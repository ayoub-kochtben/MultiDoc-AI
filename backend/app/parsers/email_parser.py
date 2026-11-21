"""EML parser: headers (metadata), body (text or HTML) and supported attachments."""
from __future__ import annotations

import tempfile
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path

from app.parsers.base import ParsedDocument, ParserError, Segment, clean_text
from app.parsers.html import html_to_markdown
from app.parsers.text import decode_bytes, split_sections

MAX_ATTACHMENT_DEPTH = 1


def _decode_part(part) -> str:
    """Decode a text part; tolerate missing/wrong charset declarations (common in hand-written .eml)."""
    raw = part.get_payload(decode=True) or b""
    declared = part.get_content_charset()
    for enc in filter(None, [declared, "utf-8"]):
        try:
            return raw.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return decode_bytes(raw)


class EmailParser:
    name = "eml"

    def __init__(self, depth: int = 0):
        self.depth = depth

    def parse(self, path: Path, filename: str) -> ParsedDocument:
        msg = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
        if not msg.keys():
            raise ParserError("Aucun en-tête e-mail trouvé : fichier EML invalide.")

        def addrs(h: str) -> list[str]:
            return [f"{n} <{a}>" if n else a for n, a in getaddresses(msg.get_all(h, []))]

        date_iso = None
        if msg["date"]:
            try:
                date_iso = parsedate_to_datetime(str(msg["date"])).isoformat()
            except (TypeError, ValueError):
                date_iso = str(msg["date"])
        meta = {
            "from": addrs("from"), "to": addrs("to"), "cc": addrs("cc"),
            "date": date_iso, "subject": str(msg["subject"] or ""), "message_id": str(msg["message-id"] or "") or None,
        }
        header_lines = [f"Sujet : {meta['subject']}", f"De : {', '.join(meta['from'])}", f"À : {', '.join(meta['to'])}"]
        if meta["cc"]:
            header_lines.append(f"Cc : {', '.join(meta['cc'])}")
        if date_iso:
            header_lines.append(f"Date : {date_iso}")

        body_part = msg.get_body(preferencelist=("plain", "html"))
        body = ""
        if body_part is not None:
            content = _decode_part(body_part)
            body = html_to_markdown(content)[0] if body_part.get_content_type() == "text/html" else content
        body = clean_text(body)

        attachments = []
        segments: list[Segment] = [Segment(text="E-mail\n" + "\n".join(header_lines), kind="email_header",
                                           meta={"section": "En-têtes"}, group="headers", atomic=True)]
        for seg in split_sections(body, markdown=False):
            seg.meta["section"] = f"Corps du message{' > ' + seg.meta['section'] if seg.meta.get('section') else ''}"
            seg.group = "body"
            segments.append(seg)

        tables = []
        for part in msg.iter_attachments():
            name = part.get_filename() or "piece_jointe"
            payload = part.get_payload(decode=True) or b""
            attachments.append({"filename": name, "content_type": part.get_content_type(), "size": len(payload)})
            if self.depth >= MAX_ATTACHMENT_DEPTH or not payload:
                continue
            sub = self._parse_attachment(name, payload)
            if sub is None:
                continue
            for seg in sub.segments:
                seg.meta = {**seg.meta, "attachment": name}
                seg.group = f"att:{name}:{seg.group}"
                segments.append(seg)
            tables.extend(sub.tables)
        meta["attachments"] = attachments
        if len(segments) == 1 and not body:
            segments[0].text += "\n(Message sans corps de texte)"
        return ParsedDocument(segments=segments, tables=tables, parser="eml/email", metadata=meta)

    def _parse_attachment(self, name: str, payload: bytes) -> ParsedDocument | None:
        from app.parsers.detection import ValidationError, detect_and_validate
        from app.parsers.registry import get_parser

        suffix = Path(name).suffix.lower()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / f"attachment{suffix}"
            p.write_bytes(payload)
            try:
                detected = detect_and_validate(p, name)
                parser = get_parser(detected.file_type, depth=self.depth + 1)
                return parser.parse(p, name)
            except (ValidationError, ParserError, Exception):  # noqa: BLE001 - attachments are best effort
                return None

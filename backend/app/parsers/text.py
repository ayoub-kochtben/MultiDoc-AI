"""TXT and Markdown parser: direct reading, section-aware splitting, line numbers preserved."""
from __future__ import annotations

import re
from pathlib import Path

from charset_normalizer import from_bytes

from app.parsers.base import ParsedDocument, ParserError, Segment

MD_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
SETEXT_UNDERLINE = re.compile(r"^(=+|-+)\s*$")


def decode_bytes(data: bytes) -> str:
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8", errors="replace")
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    best = from_bytes(data).best()
    # Short single-byte texts are ambiguous (cp1250 vs cp1252...): prefer Windows-1252 (FR/EN) when it decodes.
    if best is None or best.encoding.replace("_", "").startswith(("cp125", "iso8859", "latin", "mac")):
        try:
            return data.decode("cp1252")
        except UnicodeDecodeError:
            pass
    if best is None:
        raise ParserError("Impossible de déterminer l'encodage du fichier texte.")
    return str(best)


def read_text_file(path: Path) -> str:
    return decode_bytes(path.read_bytes())


def _looks_like_txt_heading(line: str, next_line: str | None) -> bool:
    s = line.strip()
    if not s or len(s) > 90 or s.endswith((".", ",", ";")):
        return False
    letters = [c for c in s if c.isalpha()]
    if len(letters) >= 4 and all(c.isupper() for c in letters):
        return True
    return bool(next_line is not None and SETEXT_UNDERLINE.match(next_line.strip() or "x") and next_line.strip())


def split_sections(text: str, markdown: bool) -> list[Segment]:
    """Split text into paragraph segments, each tagged with its section path and line range."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    segments: list[Segment] = []
    heading_stack: list[tuple[int, str]] = []
    buf: list[str] = []
    buf_start = 0
    in_code = False

    def section_path() -> str:
        return " > ".join(h for _, h in heading_stack)

    def flush(end_line: int) -> None:
        nonlocal buf
        content = "\n".join(buf).strip()
        if content:
            segments.append(Segment(
                text=content,
                kind="text",
                meta={"section": section_path() or None, "line_start": buf_start, "line_end": end_line},
                group=section_path(),
            ))
        buf = []

    i = 0
    while i < len(lines):
        line = lines[i]
        lineno = i + 1
        stripped = line.strip()
        if markdown and stripped.startswith("```"):
            in_code = not in_code
        heading: tuple[int, str] | None = None
        skip_next = False
        if not in_code:
            if markdown:
                m = MD_HEADING.match(stripped)
                if m:
                    heading = (len(m.group(1)), m.group(2).strip())
                elif stripped and i + 1 < len(lines) and SETEXT_UNDERLINE.match(lines[i + 1].strip() or "x") \
                        and lines[i + 1].strip():
                    heading = (1 if lines[i + 1].strip()[0] == "=" else 2, stripped)
                    skip_next = True
            elif _looks_like_txt_heading(line, lines[i + 1] if i + 1 < len(lines) else None):
                heading = (1, stripped)
                if i + 1 < len(lines) and SETEXT_UNDERLINE.match(lines[i + 1].strip() or "x") and lines[i + 1].strip():
                    skip_next = True
        if heading:
            flush(lineno - 1)
            level, title = heading
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, title))
            segments.append(Segment(
                text=("#" * level + " " + title) if markdown else title,
                kind="heading",
                meta={"section": section_path(), "line_start": lineno, "line_end": lineno + (1 if skip_next else 0)},
                group=section_path(),
            ))
            i += 2 if skip_next else 1
            buf_start = i + 1
            continue
        if not stripped and not in_code:
            flush(lineno - 1)
            buf_start = lineno + 1
        else:
            if not buf:
                buf_start = lineno
            buf.append(line.rstrip())
        i += 1
    flush(len(lines))
    return segments


class TextParser:
    name = "text"

    def parse(self, path: Path, filename: str) -> ParsedDocument:
        text = read_text_file(path)
        if not text.strip():
            raise ParserError("Le fichier texte est vide.")
        markdown = Path(filename).suffix.lower() in {".md", ".markdown"}
        segments = split_sections(text, markdown=markdown)
        title = next((s.text.lstrip("# ") for s in segments if s.kind == "heading"), None)
        return ParsedDocument(
            segments=segments,
            parser="markdown" if markdown else "text",
            metadata={"title": title, "lines": text.count("\n") + 1},
        )

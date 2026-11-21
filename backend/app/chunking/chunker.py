"""Format-aware chunking.

Parsers emit ordered segments tagged with a *group* (section, page+section, slide, sheet row block,
XPath parent, JSON path...). The chunker packs consecutive segments of the same group up to
``chunk_size`` characters, never merging across groups, splits oversized segments on sentence
boundaries with overlap, and merges citation metadata (page/line/row ranges, sections, paths).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.parsers.base import ParsedDocument, Segment
from app.rag.citations import format_location
from app.rag.guard import detect_injection

SENTENCE_SPLIT = re.compile(r"(?<=[.!?;:])\s+|\n+")
MIN_CHUNK_CHARS = 1


@dataclass
class ChunkDraft:
    content: str
    kind: str
    meta: dict[str, Any] = field(default_factory=dict)
    search_text: str = ""
    suspicious: bool = False


def _split_long(text: str, size: int, overlap: int) -> list[str]:
    """Split text into pieces <= size on sentence boundaries, with ~overlap chars carried over."""
    sentences = [s for s in SENTENCE_SPLIT.split(text) if s and s.strip()]
    pieces: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for sent in sentences:
        while len(sent) > size:  # pathological sentence: hard split on whitespace
            cut = sent.rfind(" ", 0, size)
            cut = cut if cut > size // 2 else size
            sentences_part, sent = sent[:cut], sent[cut:].lstrip()
            if cur:
                pieces.append(" ".join(cur))
                cur, cur_len = [], 0
            pieces.append(sentences_part)
        if cur_len + len(sent) + 1 > size and cur:
            pieces.append(" ".join(cur))
            carry: list[str] = []
            carry_len = 0
            for s in reversed(cur):
                if carry_len + len(s) > overlap:
                    break
                carry.insert(0, s)
                carry_len += len(s) + 1
            cur, cur_len = carry, carry_len
        cur.append(sent)
        cur_len += len(sent) + 1
    if cur:
        pieces.append(" ".join(cur))
    return pieces


def _merge_meta(segments: list[Segment]) -> dict[str, Any]:
    meta: dict[str, Any] = {}

    def rng(key_in: str, start_key: str, end_key: str, end_in: str | None = None) -> None:
        starts = [s.meta[key_in] for s in segments if s.meta.get(key_in) is not None]
        ends = [s.meta[end_in or key_in] for s in segments if s.meta.get(end_in or key_in) is not None]
        if starts:
            meta[start_key] = min(starts)
            meta[end_key] = max(ends) if ends else max(starts)

    rng("page", "page_start", "page_end")
    rng("slide", "slide_start", "slide_end")
    rng("line_start", "line_start", "line_end", "line_end")
    rng("row_start", "row_start", "row_end", "row_end")
    rng("paragraph", "paragraph_start", "paragraph_end")
    for key in ("sheet", "table", "attachment", "notes", "ocr"):
        vals = [s.meta[key] for s in segments if s.meta.get(key) not in (None, "")]
        if vals:
            meta[key] = vals[0]
    # section of the first real content segment (more specific than a parent heading)
    sections = [s.meta["section"] for s in segments if s.kind != "heading" and s.meta.get("section")]         or [s.meta["section"] for s in segments if s.meta.get("section")]
    if sections:
        meta["section"] = sections[0]
    for key in ("xpath", "json_path"):
        vals = list(dict.fromkeys(s.meta[key] for s in segments if s.meta.get(key)))
        if vals:
            meta[key] = vals[0]
            meta[f"{key}_count"] = len(vals)
            if len(vals) > 1:
                meta[f"{key}s"] = vals[:50]
    return meta


def chunk_document(parsed: ParsedDocument, filename: str, chunk_size: int = 1200, overlap: int = 150) -> list[ChunkDraft]:
    title = parsed.metadata.get("title") or parsed.metadata.get("subject")
    drafts: list[ChunkDraft] = []
    buf: list[Segment] = []
    buf_len = 0

    def emit(segs: list[Segment], text: str | None = None) -> None:
        content = (text if text is not None else "\n\n".join(s.text for s in segs)).strip()
        if len(content) < MIN_CHUNK_CHARS:
            return
        meta = _merge_meta(segs)
        kinds = {s.kind for s in segs} - {"heading"}
        kind = kinds.pop() if len(kinds) == 1 else ("mixed" if kinds else "heading")
        header = f"Document : {filename}" + (f" — {title}" if title and title not in filename else "")
        location = format_location(meta)
        drafts.append(ChunkDraft(
            content=content, kind=kind, meta=meta,
            search_text=f"{header}\nEmplacement : {location}\n{content}",
            suspicious=bool(detect_injection(content)),
        ))

    def flush() -> None:
        nonlocal buf, buf_len
        if buf:
            emit(buf)
        buf, buf_len = [], 0

    for seg in parsed.segments:
        if not seg.text.strip():
            continue
        limit = chunk_size * 4 if seg.atomic else chunk_size
        if len(seg.text) > limit:
            flush()
            prefix = ""
            if seg.atomic and "\n" in seg.text:
                # keep the first line (table label / column header) on every piece
                first, rest = seg.text.split("\n", 1)
                prefix, body = first + "\n", rest
                pieces = _split_lines(body, chunk_size * 2)
            else:
                pieces = _split_long(seg.text, chunk_size, overlap)
            for piece in pieces:
                emit([seg], prefix + piece)
            continue
        if buf and (seg.group != buf[-1].group or buf_len + len(seg.text) > chunk_size or seg.atomic or buf[-1].atomic):
            heading_only = all(s.kind == "heading" for s in buf)
            if heading_only and buf_len + len(seg.text) <= limit:
                pass  # keep (parent) headings attached to the following content
            else:
                prev = buf
                flush()
                # overlap: carry the last short segment of the same group as context
                if prev and seg.group == prev[-1].group and not prev[-1].atomic and len(prev[-1].text) <= overlap \
                        and prev[-1].kind != "heading":
                    buf, buf_len = [prev[-1]], len(prev[-1].text)
        buf.append(seg)
        buf_len += len(seg.text) + 2
    flush()
    for i, d in enumerate(drafts):
        d.meta["chunk"] = i
    return drafts


def _split_lines(text: str, size: int) -> list[str]:
    pieces, cur, cur_len = [], [], 0
    for line in text.split("\n"):
        if cur and cur_len + len(line) > size:
            pieces.append("\n".join(cur))
            cur, cur_len = [], 0
        cur.append(line[: size])
        cur_len += len(line) + 1
    if cur:
        pieces.append("\n".join(cur))
    return pieces

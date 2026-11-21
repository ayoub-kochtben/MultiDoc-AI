"""DOCX (python-docx) and PPTX (python-pptx) parsers."""
from __future__ import annotations

import re
from pathlib import Path

from app.parsers.base import ParsedDocument, ParserError, Segment, TableData, clean_text, json_safe

HEADING_STYLE = re.compile(r"^(heading|titre|título|überschrift)\s*(\d)", re.I)


def _table_to_markdown(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    out = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * width]
    out += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(out)


def rows_to_table(name: str, rows: list[list[str]], meta: dict) -> TableData | None:
    if len(rows) < 2 or len(rows[0]) < 2:
        return None
    header = [h.strip() or f"colonne_{i + 1}" for i, h in enumerate(rows[0])]
    seen: dict[str, int] = {}
    cols = []
    for h in header:
        seen[h] = seen.get(h, 0) + 1
        cols.append(h if seen[h] == 1 else f"{h}_{seen[h]}")
    data = []
    for r in rows[1:]:
        vals = []
        for v in (r + [""] * len(cols))[: len(cols)]:
            vs = v.strip().replace(" ", "")
            num = vs.replace(" ", "").replace(",", ".")
            try:
                vals.append(int(num) if re.fullmatch(r"-?\d+", num) else float(num) if re.fullmatch(r"-?\d+\.\d+", num) else (vs or None))
            except ValueError:
                vals.append(vs or None)
        data.append([json_safe(v) for v in vals])
    return TableData(name=name, columns=cols, rows=data, meta=meta)


# --------------------------------------------------------------------------------------- DOCX
class DocxParser:
    name = "docx"

    def parse(self, path: Path, filename: str) -> ParsedDocument:
        import docx
        from docx.table import Table
        from docx.text.paragraph import Paragraph

        try:
            document = docx.Document(str(path))
        except Exception as exc:  # noqa: BLE001
            raise ParserError(f"Document Word illisible : {exc}") from exc

        segments: list[Segment] = []
        tables: list[TableData] = []
        heading_stack: list[tuple[int, str]] = []
        para_no = 0
        table_no = 0

        def section() -> str:
            return " > ".join(h for _, h in heading_stack)

        for block in document.iter_inner_content():
            if isinstance(block, Paragraph):
                text = clean_text(block.text)
                if not text:
                    continue
                para_no += 1
                style = (block.style.name if block.style is not None else "") or ""
                m = HEADING_STYLE.match(style)
                level = int(m.group(2)) if m else (1 if style.lower() in {"title", "titre"} else 0)
                if level:
                    while heading_stack and heading_stack[-1][0] >= level:
                        heading_stack.pop()
                    heading_stack.append((level, text))
                    segments.append(Segment(text=text, kind="heading", meta={"section": section(), "paragraph": para_no}, group=section()))
                    continue
                kind = "list" if "list" in style.lower() else "text"
                segments.append(Segment(text=("- " + text) if kind == "list" else text, kind="text",
                                        meta={"section": section() or None, "paragraph": para_no}, group=section()))
            elif isinstance(block, Table):
                table_no += 1
                rows: list[list[str]] = []
                for row in block.rows:
                    cells, prev = [], None
                    for cell in row.cells:
                        if prev is not None and cell._tc is prev:
                            continue  # horizontally merged cell
                        prev = cell._tc
                        cells.append(" ".join(cell.text.split()))
                    rows.append(cells)
                rows = [r for r in rows if any(c for c in r)]
                if not rows:
                    continue
                meta = {"section": section() or None, "table": table_no}
                segments.append(Segment(text=f"Tableau {table_no}" + (f" (section {section()})" if section() else "") + "\n" + _table_to_markdown(rows),
                                        kind="table", meta=meta, group=f"table:{table_no}", atomic=True))
                t = rows_to_table(f"Tableau {table_no}", rows, meta)
                if t:
                    tables.append(t)

        props = document.core_properties
        if not segments:
            raise ParserError("Le document Word ne contient aucun texte.")
        return ParsedDocument(
            segments=segments, tables=tables, parser="docx/python-docx",
            metadata={k: v for k, v in {"title": props.title, "author": props.author,
                                        "created": props.created.isoformat() if props.created else None}.items() if v},
        )


# --------------------------------------------------------------------------------------- PPTX
class PptxParser:
    name = "pptx"

    def parse(self, path: Path, filename: str) -> ParsedDocument:
        from pptx import Presentation
        from pptx.enum.shapes import MSO_SHAPE_TYPE

        try:
            prs = Presentation(str(path))
        except Exception as exc:  # noqa: BLE001
            raise ParserError(f"Présentation illisible : {exc}") from exc

        segments: list[Segment] = []
        tables: list[TableData] = []

        def shape_texts(shapes, slide_no: int, out: list[str]) -> None:
            for shape in shapes:
                if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
                    shape_texts(shape.shapes, slide_no, out)
                    continue
                if getattr(shape, "has_table", False) and shape.has_table:
                    rows = [[" ".join(c.text.split()) for c in r.cells] for r in shape.table.rows]
                    out.append(_table_to_markdown(rows))
                    t = rows_to_table(f"Diapositive {slide_no} tableau", rows, {"slide": slide_no})
                    if t:
                        tables.append(t)
                    continue
                if getattr(shape, "has_text_frame", False) and shape.has_text_frame:
                    if shape == title_shape:
                        continue
                    for p in shape.text_frame.paragraphs:
                        t = " ".join("".join(r.text for r in p.runs).split())
                        if t:
                            out.append(("  " * p.level) + "- " + t if p.level or len(shape.text_frame.paragraphs) > 1 else t)

        for idx, slide in enumerate(prs.slides, start=1):
            title_shape = slide.shapes.title
            title = " ".join(title_shape.text.split()) if title_shape is not None and title_shape.has_text_frame else ""
            body: list[str] = []
            shape_texts(slide.shapes, idx, body)
            if title or body:
                text = f"Diapositive {idx}" + (f" — {title}" if title else "") + ("\n" + "\n".join(body) if body else "")
                segments.append(Segment(text=text, kind="slide", meta={"slide": idx, "section": title or None},
                                        group=f"slide:{idx}", atomic=True))
            if slide.has_notes_slide:
                notes = clean_text(slide.notes_slide.notes_text_frame.text if slide.notes_slide.notes_text_frame else "")
                if notes:
                    segments.append(Segment(text=f"Notes de la diapositive {idx}" + (f" ({title})" if title else "") + " :\n" + notes,
                                            kind="notes", meta={"slide": idx, "notes": True, "section": title or None},
                                            group=f"notes:{idx}"))
        if not segments:
            raise ParserError("La présentation ne contient aucun texte.")
        return ParsedDocument(segments=segments, tables=tables, parser="pptx/python-pptx",
                              num_pages=len(prs.slides), metadata={"slides": len(prs.slides)})

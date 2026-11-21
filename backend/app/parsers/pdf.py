"""PDF parser.

Primary engine: Docling (layout analysis, reading order, table structure, page provenance).
Scanned pages are detected with pypdfium2 (no text layer) and OCRed with Tesseract.
Fallback engine (if Docling is unavailable or fails): pypdfium2 text extraction + Tesseract OCR.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

from app.core.config import get_settings
from app.parsers.base import ParsedDocument, ParserError, Segment, TableData, clean_text, json_safe
from app.parsers.ocr import configure_tesseract, ocr_image, ocr_languages

log = logging.getLogger(__name__)
SCANNED_PAGE_MIN_CHARS = 25
_converters: dict[bool, object] = {}
_lock = threading.Lock()


def inspect_text_layer(path: Path) -> tuple[int, list[int]]:
    """Return (page count, list of 1-based page numbers without an exploitable text layer)."""
    import pypdfium2 as pdfium

    try:
        pdf = pdfium.PdfDocument(str(path))
    except pdfium.PdfiumError as exc:
        msg = str(exc)
        if "password" in msg.lower():
            raise ParserError("PDF protégé par mot de passe : impossible de l'analyser.") from exc
        raise ParserError(f"PDF corrompu ou illisible : {msg}") from exc
    try:
        scanned = []
        for i in range(len(pdf)):
            textpage = pdf[i].get_textpage()
            if len(textpage.get_text_range().strip()) < SCANNED_PAGE_MIN_CHARS:
                scanned.append(i + 1)
        return len(pdf), scanned
    finally:
        pdf.close()


def _get_converter(do_ocr: bool):
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import OcrMode, PdfPipelineOptions, TesseractCliOcrOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    with _lock:
        if do_ocr not in _converters:
            opts = PdfPipelineOptions()
            opts.do_table_structure = True
            opts.do_ocr = do_ocr
            if do_ocr:
                opts.ocr_options = TesseractCliOcrOptions(
                    lang=ocr_languages().split("+"), tesseract_cmd=configure_tesseract(),
                    path=str(get_settings().tessdata_prefix), mode=OcrMode.FULL_PAGE,
                )
            _converters[do_ocr] = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})
        return _converters[do_ocr]


class PdfParser:
    name = "pdf"

    def parse(self, path: Path, filename: str) -> ParsedDocument:
        n_pages, scanned = inspect_text_layer(path)
        if n_pages == 0:
            raise ParserError("Le PDF ne contient aucune page.")
        needs_ocr = bool(scanned)
        meta = {"pages": n_pages, "scanned_pages": scanned, "ocr": needs_ocr}
        if get_settings().pdf_engine == "docling":
            try:
                return self._parse_docling(path, n_pages, needs_ocr, meta)
            except ParserError:
                raise
            except Exception as exc:  # noqa: BLE001
                log.warning("Docling a échoué sur %s (%s) : bascule sur pypdfium2", filename, exc)
                meta["docling_error"] = str(exc)[:300]
        return self._parse_fallback(path, n_pages, set(scanned), meta)

    # ------------------------------------------------------------------ Docling
    def _parse_docling(self, path: Path, n_pages: int, needs_ocr: bool, meta: dict) -> ParsedDocument:
        from docling_core.types.doc import DocItemLabel, SectionHeaderItem, TableItem, TextItem

        result = _get_converter(needs_ocr).convert(str(path))
        doc = result.document
        segments: list[Segment] = []
        tables: list[TableData] = []
        heading_stack: list[tuple[int, str]] = []
        table_no = 0

        def section() -> str:
            return " > ".join(h for _, h in heading_stack)

        skip = {DocItemLabel.PAGE_HEADER, DocItemLabel.PAGE_FOOTER}
        for item, _level in doc.iterate_items():
            label = getattr(item, "label", None)
            if label in skip:
                continue
            page = item.prov[0].page_no if getattr(item, "prov", None) else None
            if isinstance(item, TableItem):
                table_no += 1
                md = item.export_to_markdown(doc=doc)
                if not md.strip():
                    continue
                tmeta = {"page": page, "section": section() or None, "table": table_no}
                segments.append(Segment(text=f"Tableau {table_no} (page {page})\n{md}", kind="table", meta=tmeta,
                                        group=f"table:{table_no}", atomic=True))
                try:
                    df = item.export_to_dataframe(doc=doc)
                    if len(df.columns) >= 2 and len(df) >= 1:
                        tables.append(TableData(
                            name=f"Tableau {table_no} p{page}", columns=[str(c) for c in df.columns],
                            rows=[[json_safe(_num(v)) for v in r] for r in df.itertuples(index=False, name=None)],
                            meta=tmeta,
                        ))
                except Exception:  # noqa: BLE001
                    pass
                continue
            if not isinstance(item, TextItem):
                continue
            text = clean_text(item.text)
            if not text:
                continue
            if isinstance(item, SectionHeaderItem) or label == DocItemLabel.TITLE:
                level = 0 if label == DocItemLabel.TITLE else getattr(item, "level", 1)
                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()
                heading_stack.append((level, text))
                segments.append(Segment(text=text, kind="heading", meta={"page": page, "section": section()},
                                        group=f"p{page}:{section()}"))
                continue
            if label == DocItemLabel.LIST_ITEM and not text.startswith(("-", "•")):
                text = "- " + text
            segments.append(Segment(text=text, meta={"page": page, "section": section() or None, "ocr": meta["ocr"] or None},
                                    group=f"p{page}:{section()}"))
        if not segments:
            raise ParserError("Aucun texte extrait du PDF (même après OCR).")
        return ParsedDocument(segments=segments, tables=tables, parser="pdf/docling" + ("+tesseract" if needs_ocr else ""),
                              num_pages=n_pages, metadata=meta)

    # ----------------------------------------------------------------- Fallback
    def _parse_fallback(self, path: Path, n_pages: int, scanned: set[int], meta: dict) -> ParsedDocument:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(str(path))
        segments: list[Segment] = []
        try:
            for i in range(n_pages):
                page_no = i + 1
                page = pdf[i]
                if page_no in scanned:
                    img = page.render(scale=300 / 72).to_pil()
                    paragraphs, _conf = ocr_image(img)
                    ocr = True
                else:
                    raw = page.get_textpage().get_text_range()
                    paragraphs = [p for p in clean_text(raw).split("\n\n") if p.strip()]
                    ocr = False
                for p in paragraphs:
                    segments.append(Segment(text=clean_text(p), meta={"page": page_no, "ocr": ocr or None}, group=f"p{page_no}"))
        finally:
            pdf.close()
        if not segments:
            raise ParserError("Aucun texte extrait du PDF (même après OCR).")
        return ParsedDocument(segments=segments, parser="pdf/pypdfium2" + ("+tesseract" if scanned else ""),
                              num_pages=n_pages, metadata=meta)


def _num(v):
    if isinstance(v, str):
        s = v.strip().replace(" ", "").replace(" ", "")
        try:
            return int(s)
        except ValueError:
            try:
                return float(s.replace(",", "."))
            except ValueError:
                return v.strip()
    return v

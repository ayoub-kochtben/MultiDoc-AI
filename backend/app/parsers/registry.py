"""Format -> parser registry."""
from __future__ import annotations

from app.parsers.base import DocumentParser


def get_parser(file_type: str, depth: int = 0) -> DocumentParser:
    if file_type == "pdf":
        from app.parsers.pdf import PdfParser
        return PdfParser()
    if file_type == "docx":
        from app.parsers.office import DocxParser
        return DocxParser()
    if file_type == "pptx":
        from app.parsers.office import PptxParser
        return PptxParser()
    if file_type == "xlsx":
        from app.parsers.tabular import SpreadsheetParser
        return SpreadsheetParser()
    if file_type == "csv":
        from app.parsers.tabular import CsvParser
        return CsvParser()
    if file_type == "xml":
        from app.parsers.structured import XmlParser
        return XmlParser()
    if file_type == "json":
        from app.parsers.structured import JsonParser
        return JsonParser()
    if file_type == "html":
        from app.parsers.html import HtmlParser
        return HtmlParser()
    if file_type in ("txt", "md"):
        from app.parsers.text import TextParser
        return TextParser()
    if file_type == "image":
        from app.parsers.image import ImageParser
        return ImageParser()
    if file_type == "eml":
        from app.parsers.email_parser import EmailParser
        return EmailParser(depth=depth)
    raise ValueError(f"Aucun parser pour le type {file_type}")

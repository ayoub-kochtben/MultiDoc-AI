"""Image parser: OCR with Tesseract (multi-frame TIFF/GIF supported, one page per frame)."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageSequence

from app.parsers.base import ParsedDocument, ParserError, Segment
from app.parsers.ocr import ocr_image

MAX_FRAMES = 200


class ImageParser:
    name = "image"

    def parse(self, path: Path, filename: str) -> ParsedDocument:
        segments: list[Segment] = []
        confidences: list[float] = []
        with Image.open(path) as img:
            size = img.size
            for page_no, frame in enumerate(ImageSequence.Iterator(img), start=1):
                if page_no > MAX_FRAMES:
                    break
                paragraphs, conf = ocr_image(frame.copy())
                confidences.append(conf)
                for p_no, para in enumerate(paragraphs, start=1):
                    segments.append(Segment(text=para, meta={"page": page_no, "paragraph": p_no, "ocr": True},
                                            group=f"page:{page_no}"))
        if not segments:
            raise ParserError("Aucun texte détecté par l'OCR dans l'image.")
        return ParsedDocument(
            segments=segments, parser="image/tesseract", num_pages=len(confidences),
            metadata={"ocr_confidence": round(sum(confidences) / len(confidences), 1), "width": size[0], "height": size[1]},
        )

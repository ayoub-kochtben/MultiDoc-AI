"""Tesseract OCR helpers (images and scanned PDF pages)."""
from __future__ import annotations

import os
import shutil
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageOps

from app.core.config import get_settings
from app.parsers.base import ParserError

WINDOWS_DEFAULT = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")


@lru_cache
def configure_tesseract() -> str:
    import pytesseract

    settings = get_settings()
    cmd = settings.tesseract_cmd or shutil.which("tesseract") or (str(WINDOWS_DEFAULT) if WINDOWS_DEFAULT.exists() else None)
    if not cmd:
        raise ParserError("Tesseract OCR est introuvable. Installez-le ou définissez TESSERACT_CMD.")
    pytesseract.pytesseract.tesseract_cmd = cmd
    if settings.tessdata_prefix.exists():
        os.environ["TESSDATA_PREFIX"] = str(settings.tessdata_prefix)
    return cmd


def available_languages() -> list[str]:
    import pytesseract

    configure_tesseract()
    return pytesseract.get_languages(config="")


def ocr_languages() -> str:
    wanted = get_settings().ocr_languages.split("+")
    have = set(available_languages())
    langs = [lang for lang in wanted if lang in have] or ["eng"]
    return "+".join(langs)


def prepare_image(img: Image.Image) -> Image.Image:
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("L", "RGB"):
        img = img.convert("RGB")
    img = ImageOps.grayscale(img)
    # Tesseract works best around 300 DPI: upscale small images.
    if min(img.size) < 1000:
        factor = min(3.0, 1000 / max(1, min(img.size)))
        img = img.resize((int(img.width * factor), int(img.height * factor)), Image.LANCZOS)
    return img


def ocr_image(img: Image.Image) -> tuple[list[str], float]:
    """Return (paragraphs, mean confidence 0-100)."""
    import pytesseract

    configure_tesseract()
    data = pytesseract.image_to_data(prepare_image(img), lang=ocr_languages(), config="--psm 3",
                                     output_type=pytesseract.Output.DICT)
    paragraphs: dict[tuple[int, int, int], dict[int, list[str]]] = {}
    confs: list[float] = []
    for i, word in enumerate(data["text"]):
        word = (word or "").strip()
        conf = float(data["conf"][i])
        if not word or conf < 0:
            continue
        confs.append(conf)
        key = (data["block_num"][i], data["par_num"][i], 0)
        paragraphs.setdefault(key, {}).setdefault(data["line_num"][i], []).append(word)
    out = []
    for key in sorted(paragraphs):
        lines = [" ".join(words) for _, words in sorted(paragraphs[key].items())]
        out.append("\n".join(lines))
    return out, (sum(confs) / len(confs) if confs else 0.0)

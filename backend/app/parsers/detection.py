"""File type detection and upload validation (magic bytes + extension + structure checks)."""
from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path

SUPPORTED_EXTENSIONS: dict[str, str] = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".xml": "xml",
    ".xlsx": "xlsx",
    ".xlsm": "xlsx",
    ".csv": "csv",
    ".tsv": "csv",
    ".pptx": "pptx",
    ".html": "html",
    ".htm": "html",
    ".json": "json",
    ".txt": "txt",
    ".md": "md",
    ".markdown": "md",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".tif": "image",
    ".tiff": "image",
    ".bmp": "image",
    ".webp": "image",
    ".gif": "image",
    ".eml": "eml",
}

MIME_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "xml": "application/xml",
    "csv": "text/csv",
    "html": "text/html",
    "json": "application/json",
    "txt": "text/plain",
    "md": "text/markdown",
    "eml": "message/rfc822",
}

OOXML_MAIN_PART = {"docx": "word/", "xlsx": "xl/", "pptx": "ppt/"}
TEXT_TYPES = {"xml", "csv", "html", "json", "txt", "md", "eml"}
MAX_ZIP_UNCOMPRESSED = 1024 * 1024 * 1024  # 1 GiB
MAX_ZIP_RATIO = 200

IMAGE_MAGIC = (
    b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"II*\x00", b"MM\x00*", b"BM", b"GIF87a", b"GIF89a",
)


class ValidationError(Exception):
    pass


@dataclass
class DetectedType:
    file_type: str
    mime_type: str


def detect_and_validate(path: Path, filename: str) -> DetectedType:
    """Detect the real file type and reject invalid, spoofed or dangerous files."""
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValidationError(
            f"Extension « {ext or '(aucune)'} » non supportée. Formats acceptés : "
            + ", ".join(sorted(SUPPORTED_EXTENSIONS))
        )
    declared = SUPPORTED_EXTENSIONS[ext]
    size = path.stat().st_size
    if size == 0:
        raise ValidationError("Le fichier est vide.")

    with open(path, "rb") as fh:
        head = fh.read(8192)

    if head.startswith(b"MZ") or head.startswith(b"\x7fELF"):
        raise ValidationError("Fichier exécutable refusé.")

    if declared == "pdf":
        if b"%PDF-" not in head[:1024]:
            raise ValidationError("Le fichier n'est pas un PDF valide (signature %PDF absente).")
        return DetectedType("pdf", MIME_TYPES["pdf"])

    if declared in OOXML_MAIN_PART:
        _validate_ooxml(path, declared)
        return DetectedType(declared, MIME_TYPES[declared])

    if declared == "image":
        if not (any(head.startswith(m) for m in IMAGE_MAGIC) or (head[:4] == b"RIFF" and head[8:12] == b"WEBP")):
            raise ValidationError("Le fichier n'est pas une image reconnue.")
        from PIL import Image

        try:
            with Image.open(path) as img:
                img.verify()
        except Exception as exc:  # noqa: BLE001
            raise ValidationError(f"Image corrompue : {exc}") from exc
        return DetectedType("image", f"image/{ext.lstrip('.').replace('jpg', 'jpeg')}")

    if declared in TEXT_TYPES:
        if b"\x00" in head and not (head.startswith(b"\xff\xfe") or head.startswith(b"\xfe\xff")):
            raise ValidationError("Le fichier contient des données binaires et n'est pas un fichier texte.")
        if head.startswith(b"%PDF-") or head.startswith(b"PK\x03\x04"):
            raise ValidationError("Le contenu ne correspond pas à l'extension déclarée.")
        return DetectedType(declared, MIME_TYPES[declared])

    raise ValidationError("Type de fichier non reconnu.")  # pragma: no cover


def _validate_ooxml(path: Path, kind: str) -> None:
    if not zipfile.is_zipfile(path):
        raise ValidationError(f"Le fichier .{kind} n'est pas une archive Office Open XML valide.")
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            if "[Content_Types].xml" not in names:
                raise ValidationError("Archive Office invalide ([Content_Types].xml absent).")
            if not any(n.startswith(OOXML_MAIN_PART[kind]) for n in names):
                raise ValidationError(f"Le contenu ne correspond pas à un fichier .{kind}.")
            total = sum(i.file_size for i in zf.infolist())
            compressed = sum(i.compress_size for i in zf.infolist()) or 1
            if total > MAX_ZIP_UNCOMPRESSED or total / compressed > MAX_ZIP_RATIO:
                raise ValidationError("Archive suspecte (taux de compression anormal - zip bomb ?).")
    except zipfile.BadZipFile as exc:
        raise ValidationError(f"Archive corrompue : {exc}") from exc

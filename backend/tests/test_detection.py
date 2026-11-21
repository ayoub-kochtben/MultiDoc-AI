import io
import zipfile

import pytest

from app.parsers.detection import ValidationError, detect_and_validate


def test_detects_every_corpus_file(corpus):
    expected = {".txt": "txt", ".html": "html", ".json": "json", ".xml": "xml", ".md": "md", ".csv": "csv",
                ".eml": "eml", ".docx": "docx", ".pdf": "pdf", ".xlsx": "xlsx", ".pptx": "pptx"}
    for f in corpus.iterdir():
        if f.suffix in expected:
            assert detect_and_validate(f, f.name).file_type == expected[f.suffix], f.name


def test_rejects_unknown_extension(tmp_file):
    with pytest.raises(ValidationError, match="non supportée"):
        detect_and_validate(tmp_file("a.exe", b"binary"), "a.exe")


def test_rejects_empty_file(tmp_file):
    with pytest.raises(ValidationError, match="vide"):
        detect_and_validate(tmp_file("a.txt", b""), "a.txt")


def test_rejects_executable_disguised_as_text(tmp_file):
    with pytest.raises(ValidationError, match="exécutable"):
        detect_and_validate(tmp_file("a.txt", b"\x7fELF\x02\x01\x01\x00"), "a.txt")


def test_rejects_fake_pdf(tmp_file):
    with pytest.raises(ValidationError, match="PDF"):
        detect_and_validate(tmp_file("a.pdf", "pas un pdf"), "a.pdf")


def test_rejects_pdf_renamed_as_docx(tmp_file):
    with pytest.raises(ValidationError):
        detect_and_validate(tmp_file("a.docx", b"%PDF-1.7\n..."), "a.docx")


def test_rejects_xlsx_renamed_as_docx(corpus, tmp_file):
    data = (corpus / "10_metrics.xlsx").read_bytes()
    with pytest.raises(ValidationError, match="docx"):
        detect_and_validate(tmp_file("x.docx", data), "x.docx")


def test_rejects_binary_in_text(tmp_file):
    with pytest.raises(ValidationError, match="binaires"):
        detect_and_validate(tmp_file("a.csv", b"a,b\x00\x01\x02"), "a.csv")


def test_rejects_zip_bomb(tmp_file):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("word/document.xml", b"0" * (50 * 1024 * 1024))
    with pytest.raises(ValidationError, match="zip bomb"):
        detect_and_validate(tmp_file("bomb.docx", buf.getvalue()), "bomb.docx")


def test_rejects_corrupted_image(tmp_file):
    with pytest.raises(ValidationError):
        detect_and_validate(tmp_file("a.png", b"\x89PNG\r\n\x1a\nGARBAGE"), "a.png")

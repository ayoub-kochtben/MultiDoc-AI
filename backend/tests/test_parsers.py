"""One test group per parser, on the shared corpus (doc/) and on generated edge cases."""
import io
import json
from email.message import EmailMessage
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from app.chunking.chunker import chunk_document
from app.parsers import ParserError, detect_and_validate, get_parser
from app.rag.citations import format_location


def parse(path: Path, name: str | None = None):
    name = name or path.name
    return get_parser(detect_and_validate(path, name).file_type).parse(path, name)


def all_text(parsed) -> str:
    return "\n".join(s.text for s in parsed.segments)


def _text_image(lines: list[str], size=(1400, 500)) -> Image.Image:
    img = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 40)
    except OSError:
        font = ImageFont.load_default(size=40)
    for i, line in enumerate(lines):
        draw.text((40, 40 + i * 70), line, fill="black", font=font)
    return img


# ------------------------------------------------------------------------------ TXT / MD
def test_txt(corpus):
    p = parse(corpus / "01_company_profile.txt")
    text = all_text(p)
    assert "Salma Ben Ali" in text and "2018" in text
    assert p.segments[0].meta["line_start"] == 1


def test_txt_non_utf8_and_headings(tmp_file):
    p = parse(tmp_file("legacy.txt", "INTRODUCTION\nPremière partie très détaillée.\n\nCONCLUSION\nFin.".encode("cp1252")))
    assert "Première partie" in all_text(p)
    sections = {s.meta.get("section") for s in p.segments if s.kind == "text"}
    assert sections == {"INTRODUCTION", "CONCLUSION"}


def test_markdown_sections_and_lines(corpus):
    p = parse(corpus / "05_notes.md")
    risk = next(s for s in p.segments if "QA" in s.text)
    assert risk.meta["section"].endswith("Risques")
    assert risk.meta["line_start"] >= 8


def test_markdown_code_block_hash_is_not_heading(tmp_file):
    p = parse(tmp_file("c.md", "# Titre\n\n```\n# pas un titre\n```\n"))
    assert [s.text for s in p.segments if s.kind == "heading"] == ["# Titre"]


# ------------------------------------------------------------------------------ HTML
def test_html_main_content_with_sections(corpus):
    p = parse(corpus / "02_policy.html")
    text = all_text(p)
    assert "14 jours" in text and "support@novatech.example" in text
    assert any(s.meta.get("section", "").endswith("Renouvellement") for s in p.segments)
    assert p.metadata["title"]


def test_html_drops_scripts(tmp_file):
    html = "<html><body><script>alert('x')</script><nav>Menu</nav><article><h1>Titre</h1><p>Texte utile du corps principal de la page.</p></article></body></html>"
    text = all_text(parse(tmp_file("p.html", html)))
    assert "Texte utile" in text and "alert" not in text


# ------------------------------------------------------------------------------ JSON
def test_json_paths_and_table(corpus):
    p = parse(corpus / "03_data.json")
    sec = next(s for s in p.segments if s.meta["json_path"] == "$.security")
    assert "mfa_required: true" in sec.text and "password_min_length: 12" in sec.text
    dev = next(s for s in p.segments if s.meta["json_path"] == "$.departments[0]")
    assert "employees: 16" in dev.text
    [table] = p.tables
    assert table.columns == ["name", "manager", "employees"] and sum(r[2] for r in table.rows) == 42


def test_json_lines_and_invalid(tmp_file):
    p = parse(tmp_file("a.json", '{"a": 1}\n{"a": 2}\n'))
    assert len(p.tables) == 1 and len(p.tables[0].rows) == 2
    with pytest.raises(ParserError):
        parse(tmp_file("b.json", "{not json"))


# ------------------------------------------------------------------------------ XML
def test_xml_records_xpath_and_table(corpus):
    p = parse(corpus / "04_records.xml")
    pending = next(s for s in p.segments if "Pending" in s.text)
    assert pending.meta["xpath"] == "/orders/order[2]" and "quantity: 5" in pending.text
    [t] = p.tables
    assert t.columns[0] == "id" and [r[3] for r in t.rows] == [3, 5, 2]


def test_xml_rejects_external_entities(tmp_file):
    xxe = '<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file:///C:/Windows/win.ini">]><r><a>&x;</a><b>ok</b></r>'
    p = parse(tmp_file("x.xml", xxe))
    assert "[fonts]" not in all_text(p).lower()


# ------------------------------------------------------------------------------ CSV / XLSX
def test_csv_numeric_columns_and_rows(corpus):
    p = parse(corpus / "06_customers.csv")
    [t] = p.tables
    assert sum(r[4] for r in t.rows) == 3840
    summary = next(s for s in p.segments if s.kind == "table_summary")
    assert "somme=3840" in summary.text
    rows = next(s for s in p.segments if s.kind == "rows")
    assert rows.meta["row_start"] == 2 and "Ligne 6 : id: C005" in rows.text


def test_csv_semicolon_and_decimal_comma(tmp_file):
    p = parse(tmp_file("fr.csv", "produit;prix\nA;1,5\nB;2,5\n"))
    assert p.tables[0].rows == [["A", 1.5], ["B", 2.5]]


def test_xlsx_sheets_rows_and_stats(corpus):
    p = parse(corpus / "10_metrics.xlsx")
    names = [t.name for t in p.tables]
    assert names == ["Ventes", "Support"]
    ventes = p.tables[0]
    assert sum(r[4] for r in ventes.rows) == 7800
    assert sum(r[2] for r in ventes.rows if r[1] == "NovaDesk Pro") == 55
    support = next(s for s in p.segments if s.kind == "table_summary" and s.meta["sheet"] == "Support")
    assert "moyenne=2.75" in support.text and "Résolu=4" in support.text


def test_xlsx_title_rows_are_preamble(tmp_dir):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Data"
    ws.append(["Rapport annuel"])
    ws.append([])
    ws.append(["Nom", "Valeur"])
    ws.append(["a", 1])
    ws.append(["b", 2])
    path = tmp_dir / "t.xlsx"
    wb.save(path)
    p = parse(path)
    assert p.tables[0].columns == ["Nom", "Valeur"] and p.tables[0].rows == [["a", 1], ["b", 2]]
    assert "Rapport annuel" in p.segments[0].text


# ------------------------------------------------------------------------------ DOCX
def test_docx_headings_paragraphs(corpus):
    p = parse(corpus / "08_report.docx")
    ca = next(s for s in p.segments if "185 000" in s.text)
    assert "troisième trimestre" in ca.meta["section"]


def test_docx_tables(tmp_dir):
    import docx
    d = docx.Document()
    d.add_heading("Budget", level=1)
    t = d.add_table(rows=3, cols=2)
    for i, row in enumerate([["Poste", "Montant"], ["Serveurs", "1 200"], ["Licences", "800"]]):
        for j, v in enumerate(row):
            t.cell(i, j).text = v
    path = tmp_dir / "b.docx"
    d.save(path)
    p = parse(path)
    table_seg = next(s for s in p.segments if s.kind == "table")
    assert "| Serveurs | 1 200 |" in table_seg.text and table_seg.meta["section"] == "Budget"
    assert p.tables[0].rows == [["Serveurs", 1200], ["Licences", 800]]


# ------------------------------------------------------------------------------ PPTX
def test_pptx_slides(corpus):
    p = parse(corpus / "11_presentation.pptx")
    s2 = next(s for s in p.segments if s.meta.get("slide") == 2)
    assert "Priorités stratégiques" in s2.text and "MFA" in s2.text
    assert p.num_pages == 3


def test_pptx_notes(tmp_dir):
    from pptx import Presentation
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = "Titre"
    slide.placeholders[1].text = "Point clé"
    slide.notes_slide.notes_text_frame.text = "Note de l'orateur importante"
    path = tmp_dir / "n.pptx"
    prs.save(path)
    p = parse(path)
    notes = next(s for s in p.segments if s.kind == "notes")
    assert notes.meta["notes"] and notes.meta["slide"] == 1 and "orateur" in notes.text


# ------------------------------------------------------------------------------ EML
def test_eml_metadata_and_body(corpus):
    p = parse(corpus / "07_email.eml")
    assert p.metadata["subject"] == "Maintenance planifiée"
    assert p.metadata["date"].startswith("2026-11-16")
    assert "prévue le 22 novembre 2026 de 01:00 à 03:00" in all_text(p)


def test_eml_html_body_and_attachment(tmp_file):
    msg = EmailMessage()
    msg["From"] = "Alice <alice@example.com>"
    msg["To"] = "bob@example.com"
    msg["Subject"] = "Rapport"
    msg.set_content("Version texte")
    msg.add_alternative("<html><body><p>Corps <b>HTML</b> du message.</p></body></html>", subtype="html")
    msg.add_attachment(b"col,val\nx,41\ny,1\n", maintype="text", subtype="csv", filename="data.csv")
    p = parse(tmp_file("m.eml", bytes(msg)))
    assert p.metadata["attachments"][0]["filename"] == "data.csv"
    att = [s for s in p.segments if s.meta.get("attachment") == "data.csv"]
    assert att and "somme=42" in att[0].text


# ------------------------------------------------------------------------------ PDF
def test_pdf_docling_pages_sections(corpus):
    p = parse(corpus / "09_contract.pdf")
    assert p.parser.startswith("pdf/docling")
    s = next(s for s in p.segments if "30 novembre 2027" in s.text)
    assert s.meta["page"] == 1 and "Durée" in s.meta["section"]


def test_pdf_scanned_uses_ocr(tmp_dir):
    img = _text_image(["Facture numero 4521", "Montant total : 980 dinars"])
    path = tmp_dir / "scan.pdf"
    img.save(path, "PDF", resolution=150)
    p = parse(path)
    assert p.metadata["ocr"] is True and p.metadata["scanned_pages"] == [1]
    text = all_text(p)
    assert "4521" in text and "980" in text


def test_pdf_corrupted(tmp_file):
    with pytest.raises(ParserError):
        parse(tmp_file("bad.pdf", b"%PDF-1.4\n garbage without xref"))


# ------------------------------------------------------------------------------ Images
def test_image_ocr(tmp_dir):
    path = tmp_dir / "note.png"
    _text_image(["Reunion le 12 mars", "Budget valide : 5000 TND"]).save(path)
    p = parse(path)
    text = all_text(p)
    assert "12 mars" in text and "5000" in text
    assert p.segments[0].meta["ocr"] and p.metadata["ocr_confidence"] > 50


def test_blank_image_raises(tmp_dir):
    path = tmp_dir / "blank.png"
    Image.new("RGB", (800, 600), "white").save(path)
    with pytest.raises(ParserError):
        parse(path)


# ------------------------------------------------------------------------------ Corpus-wide
def test_every_corpus_file_yields_citable_chunks(corpus):
    for f in sorted(corpus.iterdir()):
        if f.name.startswith(("12_", "README")):
            continue
        chunks = chunk_document(parse(f), f.name)
        assert chunks, f.name
        for c in chunks:
            assert c.content.strip()
            assert format_location(c.meta) != "document entier" or f.suffix == ".json", (f.name, c.meta)

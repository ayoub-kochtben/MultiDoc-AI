"""HTML parser: main-content extraction with Trafilatura, section structure preserved."""
from __future__ import annotations

from pathlib import Path

import trafilatura
from bs4 import BeautifulSoup

from app.parsers.base import ParsedDocument, ParserError, clean_text
from app.parsers.text import decode_bytes, split_sections


def html_to_markdown(html: str) -> tuple[str, dict]:
    """Return (markdown_text, metadata). Falls back to BeautifulSoup when Trafilatura finds nothing."""
    meta: dict = {}
    extracted = trafilatura.extract(
        html,
        output_format="markdown",
        include_tables=True,
        include_formatting=True,
        include_links=False,
        include_comments=False,
        favor_recall=True,
        deduplicate=False,
    )
    try:
        md = trafilatura.extract_metadata(html)
        if md is not None:
            meta = {k: v for k, v in {"title": md.title, "author": md.author, "date": md.date}.items() if v}
    except Exception:  # noqa: BLE001
        pass

    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    if not meta.get("title") and soup.title and soup.title.string:
        meta["title"] = soup.title.string.strip()

    fallback = _soup_to_markdown(soup)
    # Trafilatura may drop headings or short pages; keep whichever is more complete.
    if not extracted or len(extracted) < 0.5 * len(fallback):
        return fallback, {**meta, "extractor": "beautifulsoup"}
    return extracted, {**meta, "extractor": "trafilatura"}


def _soup_to_markdown(soup: BeautifulSoup) -> str:
    body = soup.body or soup
    for nav in body.find_all(["nav", "footer", "header", "aside"]):
        nav.decompose()
    out: list[str] = []
    for el in body.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "pre", "blockquote", "table", "td", "th", "div"]):
        if el.name == "div" and el.find(["p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "table", "li"]):
            continue
        if el.find_parent("table") and el.name != "table":
            continue
        if el.name == "table":
            rows = []
            for tr in el.find_all("tr"):
                cells = [" ".join(c.get_text(" ").split()) for c in tr.find_all(["td", "th"])]
                rows.append("| " + " | ".join(cells) + " |")
            if rows:
                out.append("\n".join(rows))
            continue
        text = " ".join(el.get_text(" ").split())
        if not text:
            continue
        if el.name.startswith("h"):
            out.append("#" * int(el.name[1]) + " " + text)
        elif el.name == "li":
            out.append("- " + text)
        else:
            out.append(text)
    return "\n\n".join(out)


class HtmlParser:
    name = "html"

    def parse(self, path: Path, filename: str) -> ParsedDocument:
        html = decode_bytes(path.read_bytes())
        markdown, meta = html_to_markdown(html)
        markdown = clean_text(markdown)
        if not markdown:
            raise ParserError("Aucun contenu textuel trouvé dans la page HTML.")
        segments = split_sections(markdown, markdown=True)
        for seg in segments:  # line numbers refer to extracted text, not to the HTML source
            seg.meta.pop("line_start", None)
            seg.meta.pop("line_end", None)
        return ParsedDocument(segments=segments, parser=f"html/{meta.get('extractor')}", metadata=meta)

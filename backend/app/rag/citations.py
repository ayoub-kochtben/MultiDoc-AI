"""Human-readable citation locations from chunk metadata."""
from __future__ import annotations

from typing import Any


def _range(a: Any, b: Any) -> str:
    if a is None:
        return ""
    return str(a) if b in (None, a) else f"{a}–{b}"


def format_location(meta: dict[str, Any]) -> str:
    parts: list[str] = []
    if meta.get("attachment"):
        parts.append(f"pièce jointe « {meta['attachment']} »")
    if meta.get("page_start") is not None:
        p = _range(meta["page_start"], meta.get("page_end"))
        parts.append(("pages " if "–" in p else "page ") + p)
    if meta.get("slide_start") is not None:
        s = _range(meta["slide_start"], meta.get("slide_end"))
        parts.append(("diapositives " if "–" in s else "diapositive ") + s + (" (notes)" if meta.get("notes") else ""))
    if meta.get("sheet"):
        parts.append(f"feuille « {meta['sheet']} »")
    if meta.get("row_start") is not None:
        parts.append("lignes " + _range(meta["row_start"], meta.get("row_end")))
    if meta.get("table") is not None:
        parts.append(f"tableau {meta['table']}")
    if meta.get("section"):
        parts.append(f"section « {meta['section']} »")
    if meta.get("line_start") is not None:
        parts.append(("lignes " if meta.get("line_end") not in (None, meta["line_start"]) else "ligne ")
                     + _range(meta["line_start"], meta.get("line_end")))
    if meta.get("paragraph_start") is not None and not meta.get("page_start"):
        parts.append("§ " + _range(meta["paragraph_start"], meta.get("paragraph_end")))
    if meta.get("xpath"):
        x = meta["xpath"]
        extra = meta.get("xpath_count", 1) - 1
        parts.append(f"XPath {x}" + (f" (+{extra})" if extra > 0 else ""))
    if meta.get("json_path"):
        j = meta["json_path"]
        extra = meta.get("json_path_count", 1) - 1
        parts.append(f"chemin JSON {j}" + (f" (+{extra})" if extra > 0 else ""))
    if meta.get("ocr"):
        parts.append("OCR")
    return ", ".join(parts) or "document entier"

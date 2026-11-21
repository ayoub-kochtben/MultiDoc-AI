"""XLSX / CSV parser (pandas): extraction per sheet and per row, real statistics computed with pandas."""
from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

import pandas as pd

from app.core.config import get_settings
from app.parsers.base import ParsedDocument, ParserError, Segment, TableData, format_value, json_safe
from app.parsers.text import decode_bytes

ROWS_PER_SEGMENT = 20


def _detect_header_row(raw: pd.DataFrame) -> int:
    """Index of the header row: first row (among the first 15) that is (almost) as wide as the table.
    Rows before it (titles, notes) are kept as preamble."""
    if raw.empty:
        return 0
    width = int(raw.notna().sum(axis=1).max())
    for idx in range(min(15, len(raw))):
        row = raw.iloc[idx]
        filled = row.dropna()
        if len(filled) >= max(1, width * 0.6):
            return idx
    return 0


def _frame_from_raw(raw: pd.DataFrame) -> tuple[pd.DataFrame, int, list[str]]:
    """Build a clean DataFrame from a header-less raw sheet. Returns (df, header_row_index, preamble lines)."""
    raw = raw.dropna(how="all").dropna(axis=1, how="all")
    if raw.empty:
        return raw, 0, []
    h_pos = _detect_header_row(raw.reset_index(drop=True))
    header_index = raw.index[h_pos]
    preamble = [" ".join(format_value(v) for v in raw.loc[i].dropna()) for i in raw.index[:h_pos]]
    header = raw.loc[header_index].tolist()
    cols: list[str] = []
    for i, h in enumerate(header):
        name = format_value(h).strip() if h is not None and not (isinstance(h, float) and pd.isna(h)) else ""
        name = name or f"colonne_{i + 1}"
        base, n = name, 2
        while name in cols:
            name = f"{base}_{n}"
            n += 1
        cols.append(name)
    df = raw.loc[raw.index > header_index].copy()
    df.columns = cols
    for c in df.columns:
        if not pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_datetime64_any_dtype(df[c]):
            converted = pd.to_numeric(df[c].astype(str).str.replace(" ", "").str.replace(" ", "").str.replace(",", "."),
                                      errors="coerce")
            non_null = df[c].notna().sum()
            if non_null and converted.notna().sum() == non_null:
                df[c] = converted
    return df, int(header_index), preamble


def _summary(name: str, df: pd.DataFrame, preamble: list[str]) -> str:
    lines = [f"Tableau « {name} » : {len(df)} lignes de données, {len(df.columns)} colonnes."]
    if preamble:
        lines.append("Titre / en-tête : " + " / ".join(preamble))
    lines.append("Colonnes : " + ", ".join(f"{c} ({_dtype(df[c])})" for c in df.columns))
    for c in df.columns:
        s = df[c]
        if pd.api.types.is_numeric_dtype(s) and s.notna().any():
            lines.append(
                f"Statistiques « {c} » (calculées avec pandas) : somme={_n(s.sum())}, moyenne={_n(s.mean())}, "
                f"min={_n(s.min())}, max={_n(s.max())}, valeurs={int(s.notna().sum())}"
            )
        elif s.notna().any():
            counts = s.astype(str).value_counts()
            if 1 < len(counts) <= 15:
                lines.append(f"Répartition « {c} » : " + ", ".join(f"{k}={v}" for k, v in counts.items()))
    return "\n".join(lines)


def _dtype(s: pd.Series) -> str:
    if pd.api.types.is_integer_dtype(s):
        return "entier"
    if pd.api.types.is_numeric_dtype(s):
        return "nombre"
    if pd.api.types.is_datetime64_any_dtype(s):
        return "date"
    return "texte"


def _n(v: Any) -> str:
    v = json_safe(v)
    if isinstance(v, float):
        return f"{v:.4f}".rstrip("0").rstrip(".")
    return str(v)


def frame_to_parsed(sheets: dict[str, pd.DataFrame], file_label: str, is_csv: bool) -> tuple[list[Segment], list[TableData]]:
    settings = get_settings()
    segments: list[Segment] = []
    tables: list[TableData] = []
    for sheet_name, raw in sheets.items():
        df, header_idx, preamble = _frame_from_raw(raw)
        if df.empty or len(df.columns) == 0:
            continue
        # spreadsheet row number of each data row (1-based, as shown in Excel / text editor)
        excel_rows = [int(i) + 1 for i in df.index]
        sheet_meta = {"sheet": None if is_csv else sheet_name}
        segments.append(Segment(
            text=_summary(sheet_name if not is_csv else file_label, df, preamble),
            kind="table_summary", meta={**sheet_meta, "row_start": header_idx + 1, "row_end": excel_rows[-1]},
            group=f"summary:{sheet_name}", atomic=True,
        ))
        stored = df.head(settings.max_table_rows_stored)
        tables.append(TableData(
            name=sheet_name if not is_csv else Path(file_label).stem,
            columns=[str(c) for c in df.columns],
            rows=[[json_safe(v) for v in row] for row in stored.itertuples(index=False, name=None)],
            meta={**sheet_meta, "header_row": header_idx + 1, "total_rows": len(df), "truncated": len(df) > len(stored)},
        ))
        indexed = df.head(settings.max_table_rows_indexed)
        cols = list(df.columns)
        for start in range(0, len(indexed), ROWS_PER_SEGMENT):
            block = indexed.iloc[start:start + ROWS_PER_SEGMENT]
            rows_no = excel_rows[start:start + len(block)]
            lines = [
                f"Ligne {rn} : " + " | ".join(f"{c}: {format_value(json_safe(v))}" for c, v in zip(cols, vals) if json_safe(v) is not None)
                for rn, vals in zip(rows_no, block.itertuples(index=False, name=None))
            ]
            label = f"Feuille « {sheet_name} »" if not is_csv else f"Fichier {file_label}"
            segments.append(Segment(
                text=f"{label} — colonnes : {', '.join(map(str, cols))}\n" + "\n".join(lines),
                kind="rows", meta={**sheet_meta, "row_start": rows_no[0], "row_end": rows_no[-1]},
                group=f"rows:{sheet_name}:{start}", atomic=True,
            ))
    return segments, tables


class SpreadsheetParser:
    name = "xlsx"

    def parse(self, path: Path, filename: str) -> ParsedDocument:
        try:
            sheets = pd.read_excel(path, sheet_name=None, header=None, engine="openpyxl")
        except Exception as exc:  # noqa: BLE001
            raise ParserError(f"Classeur Excel illisible : {exc}") from exc
        segments, tables = frame_to_parsed(sheets, filename, is_csv=False)
        if not segments:
            raise ParserError("Le classeur ne contient aucune donnée.")
        return ParsedDocument(segments=segments, tables=tables, parser="xlsx/pandas",
                              metadata={"sheets": list(sheets.keys())})


class CsvParser:
    name = "csv"

    def parse(self, path: Path, filename: str) -> ParsedDocument:
        text = decode_bytes(path.read_bytes())
        if not text.strip():
            raise ParserError("Le fichier CSV est vide.")
        sample = text[:20000]
        try:
            delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
        except csv.Error:
            delimiter = "\t" if filename.lower().endswith(".tsv") else ","
        try:
            raw = pd.read_csv(io.StringIO(text), sep=delimiter, header=None, dtype=str, keep_default_na=True,
                              skip_blank_lines=False, on_bad_lines="warn")
        except Exception as exc:  # noqa: BLE001
            raise ParserError(f"CSV illisible : {exc}") from exc
        raw = raw.map(lambda v: v.strip() if isinstance(v, str) else v)
        segments, tables = frame_to_parsed({Path(filename).stem: raw}, filename, is_csv=True)
        if not segments:
            raise ParserError("Le CSV ne contient aucune donnée.")
        return ParsedDocument(segments=segments, tables=tables, parser="csv/pandas", metadata={"delimiter": delimiter})

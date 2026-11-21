"""Common data structures produced by every document parser.

A parser turns a file into ordered ``Segment`` objects (atomic units of text that carry
citation metadata such as page, section, line range, sheet/rows, slide, XPath or JSON path)
plus optional ``TableData`` (structured rows used for exact computations).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Protocol


class ParserError(Exception):
    """Raised when a file cannot be parsed (corrupted, encrypted, empty...)."""


@dataclass
class Segment:
    text: str
    kind: str = "text"  # text | heading | table | rows | table_summary | slide | notes | email_header | record
    meta: dict[str, Any] = field(default_factory=dict)
    # Segments with different group keys are never merged into the same chunk.
    group: str = ""
    # Atomic segments are never split, even if longer than the chunk size (unless huge).
    atomic: bool = False


@dataclass
class TableData:
    name: str
    columns: list[str]
    rows: list[list[Any]]
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedDocument:
    segments: list[Segment]
    parser: str
    tables: list[TableData] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    num_pages: int | None = None

    @property
    def total_chars(self) -> int:
        return sum(len(s.text) for s in self.segments)


class DocumentParser(Protocol):
    name: str

    def parse(self, path: Path, filename: str) -> ParsedDocument: ...


def json_safe(value: Any) -> Any:
    """Convert pandas/numpy/datetime scalars into JSON-serializable Python values."""
    if value is None:
        return None
    try:
        import numpy as np
        import pandas as pd

        if value is pd.NaT:
            return None
        if isinstance(value, np.generic):
            value = value.item()
        if isinstance(value, pd.Timestamp):
            return value.isoformat()
        if isinstance(value, pd.Timedelta):
            return str(value)
    except ImportError:  # pragma: no cover
        pass
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def clean_text(text: str) -> str:
    """Normalize whitespace while keeping paragraph structure."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    text = text.replace(" ", " ").replace("​", "")
    lines = [" ".join(line.split()) for line in text.split("\n")]
    out: list[str] = []
    blank = 0
    for line in lines:
        if line:
            blank = 0
            out.append(line)
        else:
            blank += 1
            if blank == 1 and out:
                out.append("")
    return "\n".join(out).strip()


def format_value(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)

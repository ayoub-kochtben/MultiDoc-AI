"""Query analysis helpers (no database access)."""
from __future__ import annotations

import re

_SPLIT_RX = re.compile(
    r"\s*(?:\?\s+|[;,]?\s+(?:et|ainsi que|puis|and)\s+(?=(?:quel(?:le)?s?|combien|qui|où|ou|quand|comment|pourquoi|"
    r"what|which|who|where|when|how|le|la|les|l'|son|sa|ses)\b))",
    re.I,
)


def split_compound_question(question: str) -> list[str]:
    parts = [p.strip(" ?") for p in _SPLIT_RX.split(question.strip()) if p and len(p.strip(" ?")) >= 8]
    return [p + " ?" for p in parts][:4] if len(parts) > 1 else [question]

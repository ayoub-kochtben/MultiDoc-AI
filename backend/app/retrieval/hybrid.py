"""Hybrid retrieval: pgvector cosine similarity + PostgreSQL full-text search, fused with RRF."""
from __future__ import annotations

import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.embeddings.embedder import embed_query

RRF_K = 60
STOPWORDS = set("""
a à au aux avec ce ces cet cette dans de des du elle elles en est et etre être il ils je la le les leur leurs lui ma mais me mes moi mon ne nos notre nous on ou où par pas pour qu que qui sa se ses son sont sur ta te tes toi ton tu un une vos votre vous y quel quelle quels quelles quoi comment combien pourquoi quand est-ce a-t-elle a-t-il t il elle ont été ete fait faire peut tout tous toute toutes plus moins tres très
the a an of to in on for and or is are was were be been what which who whom how many much when where why does do did with from by at as it its this that these those there their
""".split())


@dataclass
class Candidate:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    file_type: str
    content: str
    kind: str
    meta: dict[str, Any]
    suspicious: bool
    vector_rank: int | None = None
    vector_score: float | None = None
    keyword_rank: int | None = None
    keyword_score: float | None = None
    rrf: float = 0.0
    rerank_score: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def build_tsquery(question: str) -> str | None:
    """OR-query of meaningful terms (prefix matching for longer words). Only [a-z0-9] reach SQL."""
    words = re.findall(r"[a-z0-9]+", _strip_accents(question.lower()))
    terms: list[str] = []
    for w in words:
        if w in STOPWORDS or (len(w) < 2 and not w.isdigit()):
            continue
        term = f"{w}:*" if len(w) >= 5 and not w.isdigit() else w
        if term not in terms:
            terms.append(term)
    return " | ".join(terms[:30]) or None


def _scope_clause(document_ids: list[uuid.UUID] | None) -> str:
    return " AND c.document_id = ANY(:doc_ids)" if document_ids else ""


def vector_search(db: Session, qvec: list[float], k: int, document_ids: list[uuid.UUID] | None) -> list[tuple[uuid.UUID, float]]:
    db.execute(text("SET LOCAL hnsw.ef_search = 200"))
    rows = db.execute(text(f"""
        SELECT c.id, 1 - (c.embedding <=> CAST(:q AS vector)) AS sim
        FROM chunks c JOIN documents d ON d.id = c.document_id
        WHERE d.status = 'indexed' AND c.embedding IS NOT NULL{_scope_clause(document_ids)}
        ORDER BY c.embedding <=> CAST(:q AS vector)
        LIMIT :k
    """), {"q": str(qvec), "k": k, "doc_ids": document_ids}).all()
    return [(r[0], float(r[1])) for r in rows]


def keyword_search(db: Session, question: str, k: int, document_ids: list[uuid.UUID] | None) -> list[tuple[uuid.UUID, float]]:
    tsq = build_tsquery(question)
    if not tsq or k <= 0:
        return []
    rows = db.execute(text(f"""
        SELECT c.id, ts_rank_cd(c.tsv, q, 32) AS rank
        FROM chunks c JOIN documents d ON d.id = c.document_id, to_tsquery('simple', :tsq) q
        WHERE d.status = 'indexed' AND c.tsv @@ q{_scope_clause(document_ids)}
        ORDER BY rank DESC
        LIMIT :k
    """), {"tsq": tsq, "k": k, "doc_ids": document_ids}).all()
    return [(r[0], float(r[1])) for r in rows]


def hybrid_search(db: Session, question: str, vector_k: int, keyword_k: int, limit: int,
                  document_ids: list[uuid.UUID] | None = None) -> list[Candidate]:
    qvec = embed_query(question)
    vec = vector_search(db, qvec, vector_k, document_ids)
    kw = keyword_search(db, question, keyword_k, document_ids)
    scores: dict[uuid.UUID, dict[str, Any]] = {}
    for rank, (cid, sim) in enumerate(vec, start=1):
        scores.setdefault(cid, {"rrf": 0.0})
        scores[cid].update(vector_rank=rank, vector_score=sim)
        scores[cid]["rrf"] += 1 / (RRF_K + rank)
    for rank, (cid, r) in enumerate(kw, start=1):
        scores.setdefault(cid, {"rrf": 0.0})
        scores[cid].update(keyword_rank=rank, keyword_score=r)
        scores[cid]["rrf"] += 1 / (RRF_K + rank)
    top = sorted(scores.items(), key=lambda kv: kv[1]["rrf"], reverse=True)[:limit]
    if not top:
        return []
    rows = db.execute(text("""
        SELECT c.id, c.document_id, d.filename, d.file_type, c.content, c.kind, c.metadata, c.suspicious
        FROM chunks c JOIN documents d ON d.id = c.document_id WHERE c.id = ANY(:ids)
    """), {"ids": [cid for cid, _ in top]}).all()
    by_id = {r[0]: r for r in rows}
    out = []
    for cid, sc in top:
        r = by_id.get(cid)
        if r is None:
            continue
        out.append(Candidate(chunk_id=r[0], document_id=r[1], filename=r[2], file_type=r[3], content=r[4], kind=r[5],
                             meta=r[6] or {}, suspicious=r[7], vector_rank=sc.get("vector_rank"),
                             vector_score=sc.get("vector_score"), keyword_rank=sc.get("keyword_rank"),
                             keyword_score=sc.get("keyword_score"), rrf=sc["rrf"]))
    return out

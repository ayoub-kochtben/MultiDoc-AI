"""Runtime-tunable model & RAG engine parameters, persisted in the database."""
from __future__ import annotations

import threading

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.models import AppSetting

KEY = "rag"
_cache: RagSettings | None = None
_lock = threading.Lock()


class RagSettings(BaseModel):
    llm_model: str = "qwen2.5:7b"
    temperature: float = Field(0.1, ge=0, le=2)
    num_ctx: int = Field(8192, ge=2048, le=131072)
    max_tokens: int = Field(1024, ge=64, le=8192)
    chunk_size: int = Field(1200, ge=200, le=6000)
    chunk_overlap: int = Field(150, ge=0, le=1000)
    vector_top_k: int = Field(30, ge=1, le=200)
    keyword_top_k: int = Field(30, ge=0, le=200)
    rerank_enabled: bool = True
    rerank_candidates: int = Field(12, ge=1, le=100)
    final_top_n: int = Field(6, ge=1, le=30)
    min_rerank_score: float = Field(0.02, ge=0, le=1)
    table_qa_enabled: bool = True
    query_rewrite: bool = True
    history_turns: int = Field(4, ge=0, le=20)


def get_rag_settings(db: Session) -> RagSettings:
    global _cache
    with _lock:
        if _cache is None:
            row = db.get(AppSetting, KEY)
            _cache = RagSettings(**(row.value if row else {}))
        return _cache.model_copy()


def update_rag_settings(db: Session, values: dict) -> RagSettings:
    global _cache
    current = get_rag_settings(db)
    new = RagSettings(**{**current.model_dump(), **values})
    row = db.get(AppSetting, KEY)
    if row:
        row.value = new.model_dump()
    else:
        db.add(AppSetting(key=KEY, value=new.model_dump()))
    db.flush()
    with _lock:
        _cache = new
    return new.model_copy()

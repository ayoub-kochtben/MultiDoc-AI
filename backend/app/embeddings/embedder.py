"""BGE-M3 dense embeddings, computed locally.

Default backend: sentence-transformers in-process on CPU (~0.1 s per query), which avoids
swapping models in a small GPU shared with the LLM. Alternative backend: Ollama (``bge-m3``).
"""
from __future__ import annotations

import logging
import math
import threading
import time
from collections.abc import Callable

from app.core.config import get_settings
from app.llm.ollama_client import embed_sync

log = logging.getLogger(__name__)
MAX_EMBED_CHARS = 12000
_model = None
_lock = threading.Lock()


def _normalize(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def get_st_model():
    global _model
    with _lock:
        if _model is None:
            from sentence_transformers import SentenceTransformer

            s = get_settings()
            t0 = time.perf_counter()
            _model = SentenceTransformer(s.embedding_model, device=s.reranker_device)
            _model.max_seq_length = 1024
            log.info("Modèle d'embedding %s chargé en %.1fs", s.embedding_model, time.perf_counter() - t0)
        return _model


def _embed_batch(batch: list[str]) -> list[list[float]]:
    s = get_settings()
    if s.embedding_backend == "ollama":
        return [_normalize(v) for v in embed_sync(batch, s.ollama_embedding_model)]
    model = get_st_model()
    with _lock:
        arr = model.encode(batch, batch_size=len(batch), normalize_embeddings=True, show_progress_bar=False)
    return arr.tolist()


def embed_texts(texts: list[str], progress: Callable[[int, int], None] | None = None) -> list[list[float]]:
    s = get_settings()
    out: list[list[float]] = []
    for start in range(0, len(texts), s.embedding_batch_size):
        batch = [t[:MAX_EMBED_CHARS] for t in texts[start:start + s.embedding_batch_size]]
        vectors = _embed_batch(batch)
        if len(vectors) != len(batch):
            raise RuntimeError("Nombre d'embeddings renvoyés incohérent")
        for v in vectors:
            if len(v) != s.embedding_dim:
                raise RuntimeError(f"Dimension d'embedding inattendue : {len(v)} (attendu {s.embedding_dim})")
        out.extend(vectors)
        if progress:
            progress(len(out), len(texts))
    return out


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]

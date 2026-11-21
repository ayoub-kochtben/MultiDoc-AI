"""BGE Reranker (cross-encoder ``BAAI/bge-reranker-v2-m3``) running locally with sentence-transformers.

On CPU the model is dynamically quantized to int8 (≈2x faster, ranking preserved: r≈0.98 vs fp32
on our corpus) and pairs are scored in length-sorted mini-batches to minimize padding.
"""
from __future__ import annotations

import logging
import threading
import time

from app.core.config import get_settings

log = logging.getLogger(__name__)
_model = None
_lock = threading.Lock()
_status = {"loaded": False, "error": None, "load_seconds": None, "quantized": False}
BATCH_SIZE = 4
MAX_PASSAGE_CHARS = 1500


def get_reranker():
    global _model
    with _lock:
        if _model is None:
            import torch
            from sentence_transformers import CrossEncoder

            s = get_settings()
            t0 = time.perf_counter()
            try:
                model = CrossEncoder(s.reranker_model, max_length=512, device=s.reranker_device)
                if s.reranker_quantize and s.reranker_device == "cpu":
                    torch.ao.quantization.quantize_dynamic(model.model, {torch.nn.Linear}, dtype=torch.qint8, inplace=True)
                    _status["quantized"] = True
                model.predict([("warmup", "warmup")], show_progress_bar=False)
            except Exception as exc:
                _status["error"] = str(exc)
                raise
            _model = model
            _status.update(loaded=True, error=None, load_seconds=round(time.perf_counter() - t0, 1))
            log.info("Reranker %s chargé en %.1fs (int8=%s)", s.reranker_model, _status["load_seconds"], _status["quantized"])
        return _model


def reranker_status() -> dict:
    return {**_status, "model": get_settings().reranker_model}


def rerank(query: str, passages: list[str]) -> list[float]:
    """Relevance scores in [0, 1] (sigmoid of the cross-encoder logit), aligned with ``passages``."""
    if not passages:
        return []
    import torch

    model = get_reranker()
    order = sorted(range(len(passages)), key=lambda i: len(passages[i]))
    pairs = [(query, passages[i][:MAX_PASSAGE_CHARS]) for i in order]
    with _lock:  # inference is not guaranteed thread-safe
        scores = model.predict(pairs, batch_size=BATCH_SIZE, activation_fn=torch.nn.Sigmoid(), show_progress_bar=False)
    out = [0.0] * len(passages)
    for i, sc in zip(order, scores):
        out[i] = float(sc)
    return out

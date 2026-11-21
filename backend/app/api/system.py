from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Chunk, Conversation, DocStatus, DocTable, Document, Message
from app.db.session import get_db
from app.llm.ollama_client import OllamaError, list_models
from app.reranking.reranker import reranker_status
from app.services.settings_service import RagSettings, get_rag_settings, update_rag_settings

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health(db: Session = Depends(get_db)):
    s = get_settings()
    out: dict = {"database": "ok", "ollama": "ok", "reranker": reranker_status()}
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        out["database"] = f"erreur : {exc}"
    try:
        names = {m["name"] for m in list_models()}
        cfg = get_rag_settings(db)
        out["models"] = {
            "llm": cfg.llm_model, "llm_available": cfg.llm_model in names or f"{cfg.llm_model}:latest" in names,
            "embedding": s.embedding_model if s.embedding_backend != "ollama" else s.ollama_embedding_model,
            "embedding_backend": s.embedding_backend,
            "embedding_available": s.embedding_backend != "ollama" or s.ollama_embedding_model in names
            or f"{s.ollama_embedding_model}:latest" in names,
        }
    except OllamaError as exc:
        out["ollama"] = f"erreur : {exc}"
    try:
        from app.parsers.ocr import available_languages
        out["ocr_languages"] = available_languages()
    except Exception as exc:  # noqa: BLE001
        out["ocr_languages"] = f"erreur : {exc}"
    out["status"] = "ok" if out["database"] == "ok" and out["ollama"] == "ok" else "degraded"
    return out


@router.get("/models")
def models():
    try:
        return [{"name": m["name"], "size": m.get("size"), "family": m.get("details", {}).get("family"),
                 "parameters": m.get("details", {}).get("parameter_size")}
                for m in list_models() if "bert" not in (m.get("details", {}).get("family") or "")]
    except OllamaError as exc:
        raise HTTPException(503, str(exc)) from exc


@router.get("/settings", response_model=RagSettings)
def read_settings(db: Session = Depends(get_db)):
    return get_rag_settings(db)


@router.put("/settings", response_model=RagSettings)
def write_settings(values: RagSettings, db: Session = Depends(get_db)):
    return update_rag_settings(db, values.model_dump())


@router.post("/settings/reset", response_model=RagSettings)
def reset_settings(db: Session = Depends(get_db)):
    return update_rag_settings(db, RagSettings().model_dump())


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    by_type = dict(db.execute(select(Document.file_type, func.count()).group_by(Document.file_type)).all())
    by_status = dict(db.execute(select(Document.status, func.count()).group_by(Document.status)).all())
    totals = db.execute(select(func.count(Document.id), func.coalesce(func.sum(Document.size_bytes), 0),
                               func.coalesce(func.sum(Document.num_chunks), 0),
                               func.avg(Document.processing_seconds))).one()
    perf = db.execute(text("""
        SELECT count(*),
               avg((metadata->>'total_s')::float), avg((metadata->>'first_token_s')::float),
               avg((metadata->>'retrieval_s')::float), avg((metadata->>'rerank_s')::float),
               sum(CASE WHEN (metadata->>'not_found')::boolean THEN 1 ELSE 0 END)
        FROM messages WHERE role = 'assistant'
    """)).one()
    top_docs = db.execute(text("""
        SELECT s->>'filename' AS filename, count(*) AS n
        FROM messages m, jsonb_array_elements(m.sources) s
        WHERE m.role = 'assistant' AND (m.metadata->'cited') @> to_jsonb((s->>'n')::int)
        GROUP BY 1 ORDER BY 2 DESC LIMIT 8
    """)).all()
    activity = db.execute(text("""
        SELECT to_char(date_trunc('day', created_at), 'YYYY-MM-DD') AS day, count(*) FILTER (WHERE role = 'user') AS questions
        FROM messages WHERE created_at > now() - interval '14 days' GROUP BY 1 ORDER BY 1
    """)).all()
    return {
        "documents": {"total": totals[0], "by_type": by_type, "by_status": by_status, "total_bytes": int(totals[1]),
                      "avg_processing_s": round(totals[3], 2) if totals[3] else None,
                      "indexed": by_status.get(DocStatus.INDEXED, 0), "failed": by_status.get(DocStatus.FAILED, 0)},
        "chunks": {"total": int(totals[2]), "suspicious": db.scalar(select(func.count()).where(Chunk.suspicious.is_(True)))},
        "tables": db.scalar(select(func.count(DocTable.id))),
        "conversations": db.scalar(select(func.count(Conversation.id))),
        "messages": db.scalar(select(func.count(Message.id))),
        "answers": {"total": perf[0], "avg_total_s": _r(perf[1]), "avg_first_token_s": _r(perf[2]),
                    "avg_retrieval_s": _r(perf[3]), "avg_rerank_s": _r(perf[4]), "not_found": perf[5] or 0},
        "top_documents": [{"filename": f, "citations": n} for f, n in top_docs],
        "activity": [{"day": d, "questions": q} for d, q in activity],
    }


def _r(v):
    return round(v, 2) if v is not None else None

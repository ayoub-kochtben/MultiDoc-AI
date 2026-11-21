"""End-to-end RAG orchestration for one chat turn (streamed as events)."""
from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from starlette.concurrency import run_in_threadpool

from app.db.models import Conversation, Message
from app.db.session import session_scope
from app.llm import prompts
from app.llm.ollama_client import OllamaError, chat_complete, chat_stream
from app.rag.citations import format_location
from app.rag.table_qa import TableAnswer, TableRef, answer_with_sql, load_tables, looks_computational
from app.reranking.reranker import rerank
from app.retrieval.hybrid import Candidate, hybrid_search
from app.retrieval.query import split_compound_question
from app.services.settings_service import RagSettings, get_rag_settings

log = logging.getLogger(__name__)
CITATION_RX = re.compile(r"\[(\d+)\]")
MIN_KEEP = 3


def _excerpt(text: str, n: int = 600) -> str:
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + " …"


def _retrieve_one(question: str, cfg: RagSettings, document_ids: list[uuid.UUID] | None,
                  timings: dict[str, float]) -> list[Candidate]:
    t0 = time.perf_counter()
    with session_scope() as db:
        candidates = hybrid_search(db, question, cfg.vector_top_k, cfg.keyword_top_k,
                                   limit=max(cfg.rerank_candidates, cfg.final_top_n), document_ids=document_ids)
    timings["retrieval_s"] = round(timings.get("retrieval_s", 0) + time.perf_counter() - t0, 3)
    if not (cfg.rerank_enabled and candidates):
        return candidates[: cfg.final_top_n]
    t1 = time.perf_counter()
    pool = candidates[: cfg.rerank_candidates]
    for c, sc in zip(pool, rerank(question, [c.content for c in pool])):
        c.rerank_score = sc
    pool.sort(key=lambda c: c.rerank_score or 0, reverse=True)
    selected = [c for c in pool if (c.rerank_score or 0) >= cfg.min_rerank_score][: cfg.final_top_n]
    # The cross-encoder can under-score paraphrases ("compte rendu" vs "Réunion"): always keep a few
    # best passages and let the LLM decide (it is instructed to report missing information).
    if len(selected) < MIN_KEEP:
        selected += [c for c in pool if c not in selected][: MIN_KEEP - len(selected)]
    timings["rerank_s"] = round(timings.get("rerank_s", 0) + time.perf_counter() - t1, 3)
    return selected


def retrieve(question: str, cfg: RagSettings, document_ids: list[uuid.UUID] | None) -> tuple[list[Candidate], dict]:
    """Retrieve + rerank. Compound questions ("X et Y ?") are split so that each part gets its own
    passages instead of the dominant topic taking every slot."""
    timings: dict[str, float] = {}
    parts = split_compound_question(question)
    if len(parts) == 1:
        return _retrieve_one(question, cfg, document_ids, timings), timings
    per_part = [_retrieve_one(p, cfg, document_ids, timings) for p in parts]
    merged: list[Candidate] = []
    seen: set[uuid.UUID] = set()
    # round-robin across sub-questions, best first
    for rank in range(max(len(x) for x in per_part)):
        for lst in per_part:
            if rank < len(lst) and lst[rank].chunk_id not in seen:
                seen.add(lst[rank].chunk_id)
                merged.append(lst[rank])
    timings["sub_questions"] = len(parts)  # type: ignore[assignment]
    return merged[: max(cfg.final_top_n, MIN_KEEP * len(parts))], timings


def _source_dict(n: int, c: Candidate) -> dict[str, Any]:
    return {
        "n": n, "type": "passage", "chunk_id": str(c.chunk_id), "document_id": str(c.document_id),
        "filename": c.filename, "file_type": c.file_type, "location": format_location(c.meta), "meta": c.meta,
        "content": c.content, "excerpt": _excerpt(c.content), "suspicious": c.suspicious,
        "scores": {"rerank": c.rerank_score, "vector": c.vector_score, "keyword": c.keyword_score, "rrf": round(c.rrf, 5)},
    }


def _history(conversation_id: uuid.UUID, turns: int) -> list[dict]:
    if turns <= 0:
        return []
    with session_scope() as db:
        conv = db.get(Conversation, conversation_id)
        msgs = [m for m in conv.messages if m.role in ("user", "assistant") and m.content.strip()] if conv else []
        msgs = msgs[-turns * 2:]
        return [{"role": m.role, "content": CITATION_RX.sub("", m.content).strip()} for m in msgs]


async def rewrite_question(question: str, history: list[dict], cfg: RagSettings) -> str:
    convo = "\n".join(f"{'Utilisateur' if h['role'] == 'user' else 'Assistant'} : {h['content'][:600]}" for h in history[-6:])
    out = await chat_complete(cfg.llm_model, [
        {"role": "system", "content": prompts.REWRITE_SYSTEM},
        {"role": "user", "content": f"Historique :\n{convo}\n\nDernière question : {question}"},
    ], {"temperature": 0, "num_predict": 120, "num_ctx": 4096})
    out = out.strip().strip('"').strip()
    return out if 3 < len(out) < 500 else question


def _load_table_refs(document_ids: list[uuid.UUID] | None) -> list[TableRef]:
    with session_scope() as db:
        refs = load_tables(db, document_ids, [])
        for r in refs:  # load data before the session closes
            _ = r.doc_table.rows, r.doc_table.columns, r.doc_table.table_metadata
        db.expunge_all()
    return refs


async def _table_answer(question: str, refs: list[TableRef], cfg: RagSettings) -> tuple[TableAnswer | None, float]:
    t0 = time.perf_counter()
    try:
        ans = await answer_with_sql(question, refs, cfg.llm_model, min(cfg.num_ctx, 8192))
    except OllamaError:
        raise
    except Exception as exc:  # noqa: BLE001 - computation is an optional enrichment
        log.warning("Table QA error: %s", exc)
        ans = None
    return ans, round(time.perf_counter() - t0, 3)


def _computation_source(ans: TableAnswer) -> dict[str, Any]:
    t = ans.tables[0]
    sheet = t.doc_table.table_metadata.get("sheet")
    loc = (f"feuille « {sheet} »" if sheet else f"table « {t.doc_table.name} »") + " — calcul SQL"
    text = ans.as_text()
    return {
        "n": 0, "type": "computation", "document_id": str(t.document_id), "filename": t.filename,
        "file_type": "table", "location": loc, "sql": ans.sql, "columns": ans.columns, "rows": ans.rows[:50],
        "content": text, "excerpt": text[:600], "suspicious": False,
        "meta": {"tables": [r.doc_table.name for r in ans.tables]}, "explanation": ans.explanation, "scores": {},
    }


async def run_chat(conversation_id: uuid.UUID, question: str, document_ids: list[uuid.UUID] | None) -> AsyncIterator[dict]:
    """Yields events: status, sources, token, done, error."""
    started = time.perf_counter()
    with session_scope() as db:
        cfg = get_rag_settings(db)
    history = await run_in_threadpool(_history, conversation_id, cfg.history_turns)

    with session_scope() as db:
        db.add(Message(conversation_id=conversation_id, role="user", content=question,
                       message_metadata={"document_ids": [str(d) for d in document_ids or []]}))
        conv = db.get(Conversation, conversation_id)
        if conv and (not conv.messages or conv.title == "Nouvelle conversation"):
            conv.title = question[:80] + ("…" if len(question) > 80 else "")
        if conv:
            conv.document_ids = [str(d) for d in document_ids or []]

    meta: dict[str, Any] = {"model": cfg.llm_model}
    search_query = question
    try:
        if history and cfg.query_rewrite:
            yield {"event": "status", "data": {"stage": "rewrite", "message": "Reformulation de la question…"}}
            search_query = await rewrite_question(question, history, cfg)
            meta["rewritten_question"] = search_query

        use_tables = cfg.table_qa_enabled and looks_computational(search_query)
        refs = await run_in_threadpool(_load_table_refs, document_ids) if use_tables else []
        msg = "Recherche hybride, reranking" + (" et calcul exact sur les tableaux…" if refs else "…")
        yield {"event": "status", "data": {"stage": "retrieval", "message": msg}}

        # Retrieval+reranking (CPU) and SQL generation (LLM) are independent: run them concurrently.
        retrieval_task = asyncio.create_task(run_in_threadpool(retrieve, search_query, cfg, document_ids))
        table_task = asyncio.create_task(_table_answer(search_query, refs, cfg)) if refs else None
        try:
            selected, timings = await retrieval_task
            meta.update(timings)
            ans, table_s = await table_task if table_task else (None, None)
        except BaseException:
            for t in (retrieval_task, table_task):
                if t is not None:
                    t.cancel()
            raise
        if table_s is not None:
            meta["table_qa_s"] = table_s

        sources = [_source_dict(i, c) for i, c in enumerate(selected, start=1)]
        if ans is not None:
            sources.insert(0, _computation_source(ans))
            for i, s in enumerate(sources, start=1):
                s["n"] = i

        yield {"event": "sources", "data": [s | {"content": s["content"][:4000]} for s in sources]}

        if not sources:
            answer = prompts.NOT_FOUND_FR + (" Aucun passage n'a été trouvé dans les documents sélectionnés."
                                             if document_ids else " Aucun document n'est encore indexé.")
            yield {"event": "token", "data": answer}
        else:
            yield {"event": "status", "data": {"stage": "generation", "message": "Génération de la réponse…"}}
            messages = [{"role": "system", "content": prompts.SYSTEM_PROMPT}, *history,
                        {"role": "user", "content": prompts.build_user_message(question if not history else
                                                                               f"{question}\n(Question autonome : {search_query})", sources)}]
            t3 = time.perf_counter()
            parts: list[str] = []
            first_token = None
            async for piece in chat_stream(cfg.llm_model, messages, {
                "temperature": cfg.temperature, "num_ctx": cfg.num_ctx, "num_predict": cfg.max_tokens,
            }):
                if first_token is None:
                    first_token = time.perf_counter() - t3
                parts.append(piece)
                yield {"event": "token", "data": piece}
            answer = "".join(parts).strip()
            meta["generation_s"] = round(time.perf_counter() - t3, 3)
            meta["first_token_s"] = round(first_token or 0, 3)

        cited = sorted({int(n) for n in CITATION_RX.findall(answer) if 0 < int(n) <= len(sources)})
        meta["cited"] = cited
        meta["total_s"] = round(time.perf_counter() - started, 3)
        meta["not_found"] = prompts.NOT_FOUND_FR.lower()[:40] in answer.lower()
        with session_scope() as db:
            msg = Message(conversation_id=conversation_id, role="assistant", content=answer,
                          sources=[{k: v for k, v in s.items() if k != "content"} | {"content": s["content"][:4000]} for s in sources],
                          message_metadata=meta)
            db.add(msg)
            db.flush()
            msg_id = str(msg.id)
        yield {"event": "done", "data": {"message_id": msg_id, "meta": meta}}
    except asyncio.CancelledError:
        raise
    except OllamaError as exc:
        log.error("LLM error: %s", exc)
        yield {"event": "error", "data": {"message": f"Erreur du modèle local (Ollama) : {exc}"}}
    except Exception as exc:  # noqa: BLE001
        log.exception("Chat pipeline failed")
        yield {"event": "error", "data": {"message": f"Erreur interne : {exc}"}}

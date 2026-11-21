"""MultiDoc AI - FastAPI application entry point."""
from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import chat, documents, system
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.db.session import init_db
from app.services import ingestion

setup_logging()
log = logging.getLogger("multidoc")


def _preload_models() -> None:
    """Load local models in the background so the first question is not penalized."""
    try:
        if get_settings().embedding_backend != "ollama":
            from app.embeddings.embedder import get_st_model
            get_st_model()
        from app.reranking.reranker import get_reranker
        get_reranker()
    except Exception as exc:  # noqa: BLE001
        log.error("Préchargement des modèles impossible : %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    resumed = ingestion.resume_pending()
    if resumed:
        log.info("%d document(s) remis en file d'indexation", resumed)
    if get_settings().preload_reranker:
        threading.Thread(target=_preload_models, daemon=True, name="models-preload").start()
    yield
    ingestion.shutdown()


app = FastAPI(title="MultiDoc AI", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(system.router)

"""Static configuration (environment variables / .env).

Runtime-tunable RAG parameters live in the database (see app.services.settings_service).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    app_name: str = "MultiDoc AI"
    # Empty (default): an embedded PostgreSQL 16 + pgvector server (pgserver) is started automatically,
    # data in DATA_DIR/pgdata - no Docker, no system install. Set a URL to use an external PostgreSQL.
    database_url: str = ""
    database_name: str = "multidoc"
    ollama_url: str = "http://localhost:11434"
    data_dir: Path = BACKEND_DIR / "data"
    tessdata_prefix: Path = BACKEND_DIR / "tessdata"
    tesseract_cmd: str | None = None  # auto-detected when None
    ocr_languages: str = "fra+eng"

    # "sentence-transformers": BGE-M3 in-process on CPU (fast queries, leaves the GPU to the LLM)
    # "ollama": BGE-M3 served by Ollama (model name "bge-m3")
    embedding_backend: str = "sentence-transformers"
    embedding_model: str = "BAAI/bge-m3"
    ollama_embedding_model: str = "bge-m3"
    embedding_dim: int = 1024
    embedding_batch_size: int = 16
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    reranker_device: str = "cpu"
    reranker_quantize: bool = True
    preload_reranker: bool = True

    max_upload_mb: int = 200
    max_table_rows_stored: int = 200_000
    max_table_rows_indexed: int = 3_000
    ingestion_workers: int = 1
    pdf_engine: str = "docling"  # docling | fast

    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.upload_dir.mkdir(parents=True, exist_ok=True)
    return s

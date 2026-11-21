"""Test configuration.

Unit tests need no service. Tests marked ``integration`` start a throw-away embedded PostgreSQL
(pgserver, in a temporary DATA_DIR) and use the local Ollama server; skipped if Ollama is unavailable.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "doc"

_TEST_DATA = Path(tempfile.mkdtemp(prefix="multidoc_test_"))
os.environ["DATABASE_URL"] = ""  # always the embedded server, never the user's database
os.environ["DATABASE_NAME"] = "multidoc_test"
os.environ["DATA_DIR"] = str(_TEST_DATA)
os.environ.setdefault("PRELOAD_RERANKER", "false")

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def corpus() -> Path:
    if not CORPUS.exists():
        pytest.skip("Corpus de test doc/ absent")
    return CORPUS


@pytest.fixture()
def tmp_dir():
    # Not pytest's tmp_path: its "-current" symlink creation can hang on Windows.
    with tempfile.TemporaryDirectory(prefix="mdt_") as d:
        yield Path(d)


@pytest.fixture()
def tmp_file(tmp_dir):
    def make(name: str, content: bytes | str) -> Path:
        p = tmp_dir / name
        p.write_bytes(content.encode("utf-8") if isinstance(content, str) else content)
        return p
    return make


def _services_available() -> str | None:
    import httpx

    try:
        from app.core.config import get_settings
        from app.services.settings_service import RagSettings
        tags = httpx.get(get_settings().ollama_url + "/api/tags", timeout=3).json()
        names = {m["name"] for m in tags.get("models", [])}
        if RagSettings().llm_model not in names:
            return f"Modèle {RagSettings().llm_model} absent d'Ollama (ollama pull {RagSettings().llm_model})"
    except Exception as exc:  # noqa: BLE001
        return f"Ollama indisponible : {exc}"
    return None


@pytest.fixture(scope="session")
def services():
    reason = _services_available()
    if reason:
        pytest.skip(reason)
    from sqlalchemy import text

    from app.db.models import Base
    from app.db.session import engine, init_db

    init_db()
    with engine.begin() as conn:
        for t in reversed(Base.metadata.sorted_tables):
            conn.execute(text(f'TRUNCATE "{t.name}" CASCADE'))
    from app.services import settings_service
    settings_service._cache = None
    return True

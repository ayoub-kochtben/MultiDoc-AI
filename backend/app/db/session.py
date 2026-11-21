from __future__ import annotations

import logging
import unicodedata
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

log = logging.getLogger(__name__)
_embedded = None  # keeps the embedded server object alive for the process lifetime


def resolve_database_url() -> str:
    """Return the SQLAlchemy URL. Without DATABASE_URL, start (or join) the embedded PostgreSQL server."""
    global _embedded
    s = get_settings()
    if s.database_url:
        return s.database_url
    import pgserver
    import psycopg

    pgdata = s.data_dir / "pgdata"
    pgdata.parent.mkdir(parents=True, exist_ok=True)
    # cleanup_mode="stop": the server stops when the last process using it exits.
    _embedded = pgserver.get_server(pgdata, cleanup_mode="stop")
    admin_uri = _embedded.get_uri()  # postgresql://postgres:@127.0.0.1:<port>/postgres
    with psycopg.connect(admin_uri, autocommit=True) as conn:
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (s.database_name,)).fetchone():
            conn.execute(f'CREATE DATABASE "{s.database_name}"')
    log.info("PostgreSQL embarqué (pgserver) : %s", pgdata)
    return admin_uri.replace("postgresql://", "postgresql+psycopg://", 1).rsplit("/", 1)[0] + f"/{s.database_name}"


engine = create_engine(resolve_database_url(), pool_pre_ping=True, pool_size=10, max_overflow=10)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency."""
    with session_scope() as s:
        yield s


# Fallback when the "unaccent" contrib extension is not available (e.g. embedded server):
# an IMMUTABLE translate() covering Latin accented characters.
_ACCENTED = "àáâãäåāăąçćčďèéêëēėęěìíîïīįñńňòóôõöøōőŕřśšşťùúûüūůűųýÿźżžÀÁÂÃÄÅĀĂĄÇĆČĎÈÉÊËĒĖĘĚÌÍÎÏĪĮÑŃŇÒÓÔÕÖØŌŐŔŘŚŠŞŤÙÚÛÜŪŮŰŲÝŸŹŻŽ"
_PLAIN = "".join(unicodedata.normalize("NFKD", c)[0] for c in _ACCENTED)


def init_db() -> None:
    from app.db import models  # noqa: F401  (register mappers)
    from app.db.models import Base

    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        has_unaccent = conn.execute(text("SELECT 1 FROM pg_available_extensions WHERE name = 'unaccent'")).first()
        if has_unaccent:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS unaccent"))
            body = "SELECT public.unaccent('public.unaccent'::regdictionary, $1)"
        else:
            body = f"SELECT translate($1, '{_ACCENTED}', '{_PLAIN}')"
        conn.execute(text(
            f"CREATE OR REPLACE FUNCTION f_unaccent(text) RETURNS text AS $$ {body} $$ "
            "LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT"
        ))
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_chunks_embedding_hnsw ON chunks "
            "USING hnsw (embedding vector_cosine_ops)"
        ))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_chunks_tsv ON chunks USING gin (tsv)"))

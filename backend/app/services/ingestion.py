"""Document ingestion: upload storage, deduplication, background parsing → chunking → embedding → indexing."""
from __future__ import annotations

import hashlib
import logging
import shutil
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

import pandas as pd
from sqlalchemy import delete, select, update

from app.chunking.chunker import chunk_document
from app.core.config import get_settings
from app.db.models import Chunk, DocStatus, DocTable, Document
from app.db.session import session_scope
from app.embeddings.embedder import embed_texts
from app.parsers import ParserError, ValidationError, detect_and_validate, get_parser
from app.rag.table_qa import slug
from app.services.settings_service import get_rag_settings

log = logging.getLogger(__name__)
_executor: ThreadPoolExecutor | None = None


class DuplicateDocumentError(Exception):
    def __init__(self, existing: Document):
        super().__init__(f"Fichier identique déjà importé : {existing.filename}")
        self.existing = existing


class UploadTooLargeError(Exception):
    pass


def executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=get_settings().ingestion_workers, thread_name_prefix="ingest")
    return _executor


def shutdown() -> None:
    if _executor is not None:
        _executor.shutdown(wait=False, cancel_futures=True)


def safe_filename(name: str) -> str:
    name = Path(name.replace("\\", "/")).name.strip() or "document"
    return "".join(c for c in name if c not in '<>:"|?*\x00')[:255]


def store_upload(stream: BinaryIO, filename: str) -> Document:
    """Stream the upload to disk (size-capped), validate it, dedupe by SHA-256 and register it."""
    s = get_settings()
    filename = safe_filename(filename)
    limit = s.max_upload_mb * 1024 * 1024
    sha = hashlib.sha256()
    size = 0
    tmp = tempfile.NamedTemporaryFile(delete=False, dir=s.upload_dir, suffix=".part")
    try:
        with tmp:
            while chunk := stream.read(1024 * 1024):
                size += len(chunk)
                if size > limit:
                    raise UploadTooLargeError(f"Fichier trop volumineux (> {s.max_upload_mb} Mo).")
                sha.update(chunk)
                tmp.write(chunk)
        tmp_path = Path(tmp.name)
        detected = detect_and_validate(tmp_path, filename)
        digest = sha.hexdigest()
        with session_scope() as db:
            existing = db.scalar(select(Document).where(Document.sha256 == digest))
            if existing:
                db.expunge(existing)  # keep loaded attributes usable after the rollback
                raise DuplicateDocumentError(existing)
            dest = s.upload_dir / f"{digest}{Path(filename).suffix.lower()}"
            shutil.move(str(tmp_path), dest)
            doc = Document(filename=filename, file_type=detected.file_type, mime_type=detected.mime_type, sha256=digest,
                           size_bytes=size, storage_path=str(dest), status=DocStatus.QUEUED, progress=0.0,
                           stage_detail="En file d'attente")
            db.add(doc)
            db.flush()
            db.expunge(doc)
        return doc
    finally:
        Path(tmp.name).unlink(missing_ok=True)


def enqueue(document_id: uuid.UUID) -> None:
    executor().submit(_safe_process, document_id)


def _set(document_id: uuid.UUID, **values) -> None:
    with session_scope() as db:
        db.execute(update(Document).where(Document.id == document_id).values(**values))


def _safe_process(document_id: uuid.UUID) -> None:
    try:
        process_document(document_id)
    except Exception as exc:  # noqa: BLE001
        log.exception("Indexation échouée pour %s", document_id)
        msg = str(exc) if isinstance(exc, (ParserError, ValidationError)) else f"{type(exc).__name__}: {exc}"
        _set(document_id, status=DocStatus.FAILED, error=msg[:2000], stage_detail="Échec")


def process_document(document_id: uuid.UUID) -> None:
    t0 = time.perf_counter()
    with session_scope() as db:
        doc = db.get(Document, document_id)
        if doc is None:
            return
        path, filename, file_type = Path(doc.storage_path), doc.filename, doc.file_type
        cfg = get_rag_settings(db)
    if not path.exists():
        raise ParserError("Fichier source introuvable sur le disque.")

    _set(document_id, status=DocStatus.PARSING, progress=0.05, error=None, stage_detail=f"Extraction ({file_type})")
    parsed = get_parser(file_type).parse(path, filename)
    log.info("%s parsé par %s : %d segments, %d tables", filename, parsed.parser, len(parsed.segments), len(parsed.tables))

    _set(document_id, status=DocStatus.CHUNKING, progress=0.3, stage_detail="Découpage en chunks")
    drafts = chunk_document(parsed, filename, chunk_size=cfg.chunk_size, overlap=cfg.chunk_overlap)
    if not drafts:
        raise ParserError("Aucun contenu indexable extrait du document.")

    _set(document_id, status=DocStatus.EMBEDDING, progress=0.35, stage_detail=f"Embeddings BGE-M3 (0/{len(drafts)})")
    last = [0.0]

    def on_progress(done: int, total: int) -> None:
        now = time.perf_counter()
        if now - last[0] > 0.5 or done == total:
            last[0] = now
            _set(document_id, progress=0.35 + 0.55 * done / total, stage_detail=f"Embeddings BGE-M3 ({done}/{total})")

    vectors = embed_texts([d.search_text for d in drafts], progress=on_progress)

    _set(document_id, progress=0.93, stage_detail="Stockage pgvector")
    with session_scope() as db:
        db.execute(delete(Chunk).where(Chunk.document_id == document_id))
        db.execute(delete(DocTable).where(DocTable.document_id == document_id))
        db.add_all([
            Chunk(document_id=document_id, chunk_index=i, kind=d.kind, content=d.content, search_text=d.search_text,
                  embedding=v, chunk_metadata=d.meta, suspicious=d.suspicious, char_count=len(d.content))
            for i, (d, v) in enumerate(zip(drafts, vectors))
        ])
        stem = Path(filename).stem
        for t in parsed.tables:
            df = pd.DataFrame(t.rows, columns=t.columns)
            columns = [{"name": c, "dtype": _sql_type(df[c])} for c in t.columns] if t.columns else []
            db.add(DocTable(document_id=document_id, name=t.name, sql_name=slug(f"{stem}_{t.name}" if t.name != stem else stem),
                            columns=columns, rows=t.rows, n_rows=len(t.rows), table_metadata=t.meta))
        doc = db.get(Document, document_id)
        doc.status = DocStatus.INDEXED
        doc.progress = 1.0
        doc.stage_detail = "Indexé"
        doc.num_chunks = len(drafts)
        doc.num_pages = parsed.num_pages
        doc.parser = parsed.parser
        doc.doc_metadata = {**parsed.metadata, "tables": len(parsed.tables),
                            "suspicious_chunks": sum(d.suspicious for d in drafts), "chars": parsed.total_chars}
        doc.processing_seconds = round(time.perf_counter() - t0, 2)
        doc.indexed_at = datetime.now(timezone.utc)
    log.info("%s indexé : %d chunks en %.1fs", filename, len(drafts), time.perf_counter() - t0)


def _sql_type(s: pd.Series) -> str:
    s = s.dropna()
    if s.empty:
        return "TEXT"
    if all(isinstance(v, bool) for v in s):
        return "BOOLEAN"
    if all(isinstance(v, int) and not isinstance(v, bool) for v in s):
        return "INTEGER"
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in s):
        return "REAL"
    return "TEXT"


def reindex(document_id: uuid.UUID) -> None:
    _set(document_id, status=DocStatus.QUEUED, progress=0.0, error=None, stage_detail="Réindexation en file d'attente")
    enqueue(document_id)


def delete_document(document_id: uuid.UUID) -> bool:
    with session_scope() as db:
        doc = db.get(Document, document_id)
        if doc is None:
            return False
        path = Path(doc.storage_path)
        db.delete(doc)
    path.unlink(missing_ok=True)
    return True


def resume_pending() -> int:
    """Re-queue documents left in a processing state by a previous shutdown."""
    with session_scope() as db:
        ids = list(db.scalars(select(Document.id).where(Document.status.in_(DocStatus.PROCESSING))))
    for i in ids:
        reindex(i)
    return len(ids)

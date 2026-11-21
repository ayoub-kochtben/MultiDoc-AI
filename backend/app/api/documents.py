from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import ChunkOut, DocumentOut, UploadResult
from app.db.models import Chunk, DocStatus, DocTable, Document
from app.db.session import get_db
from app.parsers import SUPPORTED_EXTENSIONS, ValidationError
from app.rag.citations import format_location
from app.services import ingestion

router = APIRouter(prefix="/api/documents", tags=["documents"])
MAX_FILES_PER_REQUEST = 50


@router.get("", response_model=list[DocumentOut])
def list_documents(db: Session = Depends(get_db)):
    return db.scalars(select(Document).order_by(Document.created_at.desc())).all()


@router.get("/formats")
def formats():
    return {"extensions": sorted(SUPPORTED_EXTENSIONS)}


@router.post("/upload", response_model=list[UploadResult])
def upload(files: list[UploadFile] = File(...)):
    if len(files) > MAX_FILES_PER_REQUEST:
        raise HTTPException(400, f"Maximum {MAX_FILES_PER_REQUEST} fichiers par envoi.")
    results: list[UploadResult] = []
    for f in files:
        name = f.filename or "document"
        try:
            doc = ingestion.store_upload(f.file, name)
            ingestion.enqueue(doc.id)
            results.append(UploadResult(filename=name, status="accepted", document=DocumentOut.model_validate(doc)))
        except ingestion.DuplicateDocumentError as dup:
            results.append(UploadResult(filename=name, status="duplicate", document=DocumentOut.model_validate(dup.existing),
                                        detail=f"Fichier identique (SHA-256) à « {dup.existing.filename} » déjà importé."))
        except (ValidationError, ingestion.UploadTooLargeError) as exc:
            results.append(UploadResult(filename=name, status="rejected", detail=str(exc)))
        finally:
            f.file.close()
    return results


def _get(db: Session, document_id: uuid.UUID) -> Document:
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(404, "Document introuvable.")
    return doc


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(document_id: uuid.UUID, db: Session = Depends(get_db)):
    return _get(db, document_id)


@router.get("/{document_id}/chunks", response_model=list[ChunkOut])
def get_chunks(document_id: uuid.UUID, db: Session = Depends(get_db)):
    _get(db, document_id)
    chunks = db.scalars(select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.chunk_index)).all()
    return [ChunkOut(id=c.id, chunk_index=c.chunk_index, kind=c.kind, content=c.content,
                     location=format_location(c.chunk_metadata), metadata=c.chunk_metadata, suspicious=c.suspicious)
            for c in chunks]


@router.get("/{document_id}/tables")
def get_tables(document_id: uuid.UUID, db: Session = Depends(get_db)):
    _get(db, document_id)
    tables = db.scalars(select(DocTable).where(DocTable.document_id == document_id)).all()
    return [{"id": t.id, "name": t.name, "columns": t.columns, "n_rows": t.n_rows, "preview": t.rows[:20],
             "metadata": t.table_metadata} for t in tables]


@router.get("/{document_id}/file")
def download(document_id: uuid.UUID, db: Session = Depends(get_db)):
    doc = _get(db, document_id)
    return FileResponse(doc.storage_path, filename=doc.filename, media_type=doc.mime_type or "application/octet-stream")


@router.post("/{document_id}/reindex", response_model=DocumentOut)
def reindex(document_id: uuid.UUID, db: Session = Depends(get_db)):
    doc = _get(db, document_id)
    if doc.status in DocStatus.PROCESSING and doc.status != DocStatus.QUEUED:
        raise HTTPException(409, "Le document est déjà en cours d'indexation.")
    db.commit()
    ingestion.reindex(document_id)
    db.refresh(doc)
    return doc


@router.delete("/{document_id}", status_code=204)
def delete(document_id: uuid.UUID):
    if not ingestion.delete_document(document_id):
        raise HTTPException(404, "Document introuvable.")

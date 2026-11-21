from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    file_type: str
    mime_type: str | None
    sha256: str
    size_bytes: int
    status: str
    progress: float
    stage_detail: str | None
    error: str | None
    num_chunks: int
    num_pages: int | None
    parser: str | None
    metadata: dict[str, Any] = Field(validation_alias="doc_metadata")
    processing_seconds: float | None
    created_at: datetime
    indexed_at: datetime | None


class UploadResult(BaseModel):
    filename: str
    status: str  # accepted | duplicate | rejected
    document: DocumentOut | None = None
    detail: str | None = None


class ChunkOut(BaseModel):
    id: uuid.UUID
    chunk_index: int
    kind: str
    content: str
    location: str
    metadata: dict[str, Any]
    suspicious: bool


class ChatRequest(BaseModel):
    conversation_id: uuid.UUID | None = None
    message: str = Field(min_length=1, max_length=8000)
    document_ids: list[uuid.UUID] = Field(default_factory=list)


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    document_ids: list[str]
    created_at: datetime
    updated_at: datetime


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: str
    content: str
    sources: list[dict[str, Any]]
    metadata: dict[str, Any] = Field(validation_alias="message_metadata")
    created_at: datetime


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]


class ConversationUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=256)

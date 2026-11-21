from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import ChatRequest, ConversationDetail, ConversationOut, ConversationUpdate
from app.db.models import Conversation
from app.db.session import get_db, session_scope
from app.rag.pipeline import run_chat

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat")
async def chat(req: ChatRequest):
    with session_scope() as db:
        if req.conversation_id:
            conv = db.get(Conversation, req.conversation_id)
            if conv is None:
                raise HTTPException(404, "Conversation introuvable.")
        else:
            conv = Conversation(document_ids=[str(d) for d in req.document_ids])
            db.add(conv)
            db.flush()
        conversation_id = conv.id

    async def events():
        yield _sse("conversation", {"conversation_id": str(conversation_id)})
        async for ev in run_chat(conversation_id, req.message.strip(), req.document_ids or None):
            yield _sse(ev["event"], ev["data"])

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(db: Session = Depends(get_db)):
    return db.scalars(select(Conversation).order_by(Conversation.updated_at.desc())).all()


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(conversation_id: uuid.UUID, db: Session = Depends(get_db)):
    conv = db.get(Conversation, conversation_id)
    if conv is None:
        raise HTTPException(404, "Conversation introuvable.")
    return conv


@router.patch("/conversations/{conversation_id}", response_model=ConversationOut)
def rename_conversation(conversation_id: uuid.UUID, body: ConversationUpdate, db: Session = Depends(get_db)):
    conv = db.get(Conversation, conversation_id)
    if conv is None:
        raise HTTPException(404, "Conversation introuvable.")
    conv.title = body.title
    return conv


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: uuid.UUID, db: Session = Depends(get_db)):
    conv = db.get(Conversation, conversation_id)
    if conv is None:
        raise HTTPException(404, "Conversation introuvable.")
    db.delete(conv)

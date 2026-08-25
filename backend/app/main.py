import os
import io
import json
import uuid
import traceback
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, APIRouter, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from pypdf import PdfReader
from sqlalchemy.orm import Session

from app import models
from app.db import Base, engine, get_db
from app.llm import get_llm_reply, stream_llm_reply, validate_image
from app.models import Conversation, Message
from app.rag import embed_and_store, search_similar


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="AI Platform", version="0.1.0", lifespan=lifespan)

cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_router = APIRouter(prefix="/api")


class ChatRequest(BaseModel):
    conversation_id: uuid.UUID | None = None
    message: str
    image: str | None = None


def build_prompt(message: str) -> str:
    context_chunks = search_similar(message)
    if not context_chunks:
        return message
    context_text = "\n\n".join(context_chunks)
    return (
        "Answer the question using the context below if it's relevant. "
        "If the context isn't relevant, answer normally.\n\n"
        f"Context:\n{context_text}\n\nQuestion: {message}"
    )


@api_router.post("/chat")
async def chat(payload: ChatRequest, db: Session = Depends(get_db)):
    if payload.image:
        try:
            validate_image(payload.image)
        except ValueError as e:
            raise HTTPException(400, str(e))

    if payload.conversation_id:
        conversation = db.get(Conversation, payload.conversation_id)
        if not conversation:
            raise HTTPException(404, "Conversation not found")
    else:
        conversation = Conversation()
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    db.add(Message(conversation_id=conversation.id, role="user", content=payload.message))
    db.commit()

    if payload.image:
        reply_text = await get_llm_reply(payload.message, image_data_url=payload.image)
    else:
        reply_text = await get_llm_reply(build_prompt(payload.message))

    db.add(Message(conversation_id=conversation.id, role="assistant", content=reply_text))
    db.commit()

    return {"conversation_id": str(conversation.id), "reply": reply_text}


@api_router.post("/chat/stream")
async def chat_stream(payload: ChatRequest, db: Session = Depends(get_db)):
    if payload.image:
        try:
            validate_image(payload.image)
        except ValueError as e:
            raise HTTPException(400, str(e))

    if payload.conversation_id:
        conversation = db.get(Conversation, payload.conversation_id)
        if not conversation:
            raise HTTPException(404, "Conversation not found")
    else:
        conversation = Conversation()
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    db.add(Message(conversation_id=conversation.id, role="user", content=payload.message))
    db.commit()

    async def event_generator():
        full_reply = ""
        yield f"event: conversation\ndata: {conversation.id}\n\n"
        try:
            if payload.image:
                stream = stream_llm_reply(payload.message, image_data_url=payload.image)
            else:
                stream = stream_llm_reply(build_prompt(payload.message))
            async for delta in stream:
                full_reply += delta
                yield f"data: {json.dumps({'delta': delta})}\n\n"
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                error_text = "Rate limit reached on the free tier. Wait a minute and try again."
            else:
                error_text = f"Upstream error ({e.response.status_code})."
            yield f"data: {json.dumps({'delta': error_text})}\n\n"
            full_reply = error_text
        except Exception:
            traceback.print_exc()
            error_text = "Something went wrong talking to the model."
            yield f"data: {json.dumps({'delta': error_text})}\n\n"
            full_reply = error_text

        db.add(Message(conversation_id=conversation.id, role="assistant", content=full_reply))
        db.commit()
        yield "event: done\ndata: end\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@api_router.post("/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    content = await file.read()

    if file.filename.lower().endswith(".pdf"):
        reader = PdfReader(io.BytesIO(content))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    else:
        text = content.decode("utf-8", errors="ignore")

    if not text.strip():
        raise HTTPException(400, "No extractable text found in file")

    chunk_count = embed_and_store(text, file.filename)
    return {"filename": file.filename, "chunks_indexed": chunk_count}


@api_router.get("/conversations")
def list_conversations(db: Session = Depends(get_db)):
    conversations = db.query(Conversation).order_by(Conversation.created_at.desc()).all()
    result = []
    for c in conversations:
        first_message = (
            db.query(Message)
            .filter(Message.conversation_id == c.id, Message.role == "user")
            .order_by(Message.created_at.asc())
            .first()
        )
        result.append(
            {
                "id": str(c.id),
                "title": (first_message.content[:50] if first_message else "New conversation"),
                "created_at": c.created_at.isoformat(),
            }
        )
    return result


@api_router.get("/conversations/{conversation_id}/messages")
def get_conversation_messages(conversation_id: uuid.UUID, db: Session = Depends(get_db)):
    conversation = db.get(Conversation, conversation_id)
    if not conversation:
        raise HTTPException(404, "Conversation not found")
    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
        .all()
    )
    return [
        {"role": m.role, "content": m.content, "timestamp": m.created_at.isoformat()}
        for m in messages
    ]


@api_router.get("/health")
def health_check():
    return {"status": "ok"}


app.include_router(api_router)
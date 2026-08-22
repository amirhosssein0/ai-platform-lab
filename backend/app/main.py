import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from app.db import Base, engine
from app import models 
import uuid
from pydantic import BaseModel
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import Conversation, Message
from app.llm import get_llm_reply


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


@api_router.post("/chat")
async def chat(payload: ChatRequest, db: Session = Depends(get_db)):
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

    reply_text = await get_llm_reply(payload.message)

    db.add(Message(conversation_id=conversation.id, role="assistant", content=reply_text))
    db.commit()

    return {"conversation_id": str(conversation.id), "reply": reply_text}


@api_router.get("/health")
def health_check():
    return {"status": "ok"}


app.include_router(api_router)
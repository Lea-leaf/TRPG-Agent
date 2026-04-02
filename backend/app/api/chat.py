"""Chat API router."""

from uuid import uuid4

from fastapi import HTTPException
from fastapi import APIRouter

from app.api.schemas import ChatRequest, ChatResponse
from app.config.settings import settings
from app.graph.builder import build_graph
from app.memory.checkpointer import Checkpointer

router = APIRouter(prefix="/api/chat", tags=["chat"])

GRAPH = build_graph()
CHECKPOINTER = Checkpointer(settings.memory_db_path)


@router.post("", response_model=ChatResponse)
async def chat(payload: ChatRequest) -> ChatResponse:
    try:
        session_id = payload.session_id or str(uuid4())
        saved_state = CHECKPOINTER.load(session_id) or {}
        messages = saved_state.get("messages", [])
        if not isinstance(messages, list):
            messages = []

        result = GRAPH.invoke(
            {
                "session_id": session_id,
                "user_input": payload.message,
                "messages": messages,
            }
        )
        CHECKPOINTER.save(session_id, {"messages": result.get("messages", [])})

        return ChatResponse(
            reply=result.get("output", ""),
            plan=result.get("plan"),
            session_id=session_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


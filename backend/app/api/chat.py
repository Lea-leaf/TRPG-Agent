"""Chat API router."""

import sqlite3

from fastapi import HTTPException
from fastapi import APIRouter
from fastapi import status

from app.api.schemas import ChatRequest, ChatResponse
from app.services.chat_session_service import get_chat_session_service

router = APIRouter(prefix="/api/chat", tags=["chat"])

CHAT_SESSION_SERVICE = get_chat_session_service()


@router.post("", response_model=ChatResponse)
async def chat(payload: ChatRequest) -> ChatResponse:
    try:
        result = CHAT_SESSION_SERVICE.process_turn(
            message=payload.message,
            session_id=payload.session_id,
        )

        return ChatResponse(
            reply=result.get("reply", ""),
            plan=result.get("plan"),
            session_id=result.get("session_id", ""),
        )
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Conversation memory storage is unavailable.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


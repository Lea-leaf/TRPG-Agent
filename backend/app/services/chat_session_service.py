"""Chat session orchestration service for graph execution and persistence."""

from __future__ import annotations

from functools import lru_cache
from typing import Any
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage

from app.config.settings import settings
from app.graph.builder import build_graph
from app.memory.checkpointer import get_checkpointer


class ChatSessionService:
    """Coordinates graph invocation with official thread-based checkpointing."""

    def __init__(self, graph: Any) -> None:
        self._graph = graph

    def process_turn(self, message: str, session_id: str | None = None) -> dict[str, Any]:
        current_session_id = session_id or str(uuid4())

        result = self._graph.invoke(
            {
                "messages": [HumanMessage(content=message)],
                "session_id": current_session_id,
            },
            config={"configurable": {"thread_id": current_session_id}},
        )

        messages = result.get("messages", [])
        reply = ""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and not msg.tool_calls:
                reply = msg.content if isinstance(msg.content, str) else ""
                break

        return {
            "reply": reply,
            "plan": None,
            "session_id": current_session_id,
        }


@lru_cache(maxsize=1)
def get_chat_session_service() -> ChatSessionService:
    graph = build_graph(checkpointer=get_checkpointer(settings.memory_db_path))
    return ChatSessionService(graph=graph)

"""Chat session orchestration service for graph execution and persistence."""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Optional
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command

from app.config.settings import settings
from app.graph.builder import build_graph
from app.memory.checkpointer import get_checkpointer


class ChatSessionService:
    """Coordinates graph invocation with official thread-based checkpointing."""

    def __init__(self, graph: Any) -> None:
        self._graph = graph

    def process_turn(
        self,
        message: Optional[str] = None,
        session_id: Optional[str] = None,
        resume_action: Optional[str] = None,
    ) -> dict[str, Any]:
        current_session_id = session_id or str(uuid4())
        config = {"configurable": {"thread_id": current_session_id}}

        if resume_action:
            # 恢复挂起的图
            result = self._graph.invoke(Command(resume=resume_action), config=config)
        elif message:
            # 新的消息进入
            result = self._graph.invoke(
                {"messages": [HumanMessage(content=message)]},
                config=config,
            )
        else:
            raise ValueError("Must provide either message or resume_action.")

        # 获取图的当前完整状态，检查是否处于挂起状态（被 interrupt 阻塞）
        state = self._graph.get_state(config)
        pending_action = None
        if state.tasks and state.tasks[0].interrupts:
            # 如果存在中断，说明这是图在等待外部交互
            # 从 interrupt 中获取我们投出的那份 payload (如 {"type": "dice_roll", ...})
            pending_action = state.tasks[0].interrupts[0].value
        
        # 查找最新的完整 AI 回复文本
        messages = state.values.get("messages", [])
        reply = ""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and not msg.tool_calls:
                reply = msg.content if isinstance(msg.content, str) else ""
                break

        return {
            "reply": reply,
            "plan": None,
            "session_id": current_session_id,
            "pending_action": pending_action,
        }


@lru_cache(maxsize=1)
def get_chat_session_service() -> ChatSessionService:
    graph = build_graph(checkpointer=get_checkpointer(settings.memory_db_path))
    return ChatSessionService(graph=graph)

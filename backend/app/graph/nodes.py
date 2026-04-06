"""Graph node function implementations."""

from functools import lru_cache

from langchain_core.messages import AIMessage

from app.graph.state import GraphState
from app.services.llm_service import LLMService
from app.services.tool_service import get_tools

ASSISTANT_SYSTEM_PROMPT = (
    "You are a helpful TRPG assistant. "
    "Use tools when external facts are needed, otherwise answer directly."
)


@lru_cache(maxsize=1)
def _get_llm_service() -> LLMService:
    """使用 lru_cache 实现单例模式，获取大语言模型服务"""
    return LLMService()


def router_node(state: GraphState) -> GraphState:
    return {**state}


def assistant_node(state: GraphState) -> GraphState:
    messages = state.get("messages", [])
    response = _get_llm_service().invoke_with_tools(
        messages=messages,
        tools=get_tools(),
        system_prompt=ASSISTANT_SYSTEM_PROMPT,
    )

    output = response.content if isinstance(response.content, str) and not response.tool_calls else ""
    return {
        **state,
        "messages": [response],
        "output": output,
    }

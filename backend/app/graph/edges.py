"""Conditional routes and edge rules."""

from langchain_core.messages import AIMessage

from app.graph.constants import ASSISTANT_NODE, END_NODE, ROUTER_NODE, TOOL_NODE
from app.graph.state import GraphState


def route_from_router(state: GraphState) -> str:
    messages = state.get("messages", [])
    if not messages:
        return END_NODE
    return ASSISTANT_NODE


def route_from_assistant(state: GraphState) -> str:
    messages = state.get("messages", [])
    if not messages:
        return END_NODE

    last_message = messages[-1]
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return TOOL_NODE
    return END_NODE


def route_from_tool(state: GraphState) -> str:
    return ASSISTANT_NODE


ROUTE_OPTIONS = {
    ASSISTANT_NODE: ASSISTANT_NODE,
    TOOL_NODE: TOOL_NODE,
    END_NODE: END_NODE,
}


ROUTER_NODE_NAME = ROUTER_NODE


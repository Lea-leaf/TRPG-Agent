"""冒险模组工具 — 让模型按 PDF 节点图读取与推进剧情。"""

from __future__ import annotations

import json
from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from app.adventures.models import AdventureNode, AdventureState
from app.adventures.store import get_adventure_store
from app.services.skills import load_skill_content


def _adventure_dict(state: dict | None) -> dict:
    """读取当前冒险状态；空状态默认从 Lost Mine 初始节点开始。"""
    if not state:
        return AdventureState().model_dump()
    adventure = state.get("adventure")
    if not adventure:
        return AdventureState().model_dump()
    if hasattr(adventure, "model_dump"):
        return adventure.model_dump()
    return AdventureState.model_validate(adventure).model_dump()


def _node_payload(node: AdventureNode, adventure: dict) -> dict:
    """返回给模型的节点材料，显式区分玩家可见信息与 DM 私密信息。"""
    completed_events = set(adventure.get("completed_event_ids", []))
    known_clues = set(adventure.get("known_clue_ids", []))
    available_exits = []
    for exit_option in node.exits:
        missing = [item for item in exit_option.requires if item not in completed_events and item not in known_clues]
        available_exits.append(
            {
                "id": exit_option.id,
                "label": exit_option.label,
                "next_node_id": exit_option.next_node_id,
                "requires": exit_option.requires,
                "available": not missing,
                "missing": missing,
                "description": exit_option.description,
            }
        )

    return {
        "node": {
            "id": node.id,
            "title": node.title,
            "kind": node.kind,
            "source_pages": [node.page_start, node.page_end],
            "source_excerpt": node.source_excerpt,
            "source_text": node.source_text,
            "subsections": node.subsections,
            "dm_summary": node.dm_summary,
            "player_visible_intro": node.player_visible_intro,
            "secrets": node.secrets,
            "checks": node.checks,
            "encounters": [item.model_dump() for item in node.encounters],
            "rewards": node.rewards,
            "clues": node.clues,
            "events": node.events,
            "dm_guidance": node.dm_guidance,
            "candidate_exits": node.candidate_exits,
        },
        "available_exits": available_exits,
        "adventure_state": adventure,
    }


def _tool_message(payload: dict, tool_call_id: str | None) -> ToolMessage:
    """冒险工具统一输出 JSON，降低模型误读自然语言的概率。"""
    return ToolMessage(
        content=json.dumps(payload, ensure_ascii=False, indent=2),
        tool_call_id=tool_call_id,
    )


def _node_brief(node: AdventureNode, score: float | None = None) -> dict:
    """搜索结果只返回足够模型判断是否加载的摘要。"""
    payload = {
        "id": node.id,
        "title": node.title,
        "kind": node.kind,
        "source_pages": [node.page_start, node.page_end],
        "source_excerpt": node.source_excerpt,
        "dm_guidance_keys": [key for key, values in node.dm_guidance.items() if values],
        "has_encounters": bool(node.encounters),
        "clue_ids": [str(item.get("id", "")) for item in node.clues if isinstance(item, dict)],
    }
    if score is not None:
        payload["score"] = score
    return payload


@tool
def load_adventure_node(
    node_id: str | None = None,
    *,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """读取当前或指定剧情节点的主持材料。
    用于探索阶段了解当前模组场景、可见开场、DM 私密信息、遭遇、线索和可推进出口。
    参数示例：{} 读取当前节点；{"node_id": "goblin_ambush"} 读取指定节点。

    Args:
        node_id: 可选节点 ID；不传则读取当前 active_node_id。
    """
    adventure = _adventure_dict(state)
    target_node_id = node_id or adventure["active_node_id"]
    node = get_adventure_store().get_node(target_node_id)
    if target_node_id not in adventure["unlocked_node_ids"]:
        adventure["unlocked_node_ids"].append(target_node_id)

    payload = _node_payload(node, adventure)
    return Command(
        update={
            "adventure": adventure,
            "messages": [_tool_message(payload, tool_call_id)],
        }
    )


@tool
def inspect_adventure_state(
    include_help: bool = False,
    *,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """查看当前冒险进度；如需完整主持流程说明，传 include_help=True。
    参数示例：{}；加载说明用 {"include_help": true}。
    """
    if include_help:
        return Command(update={"messages": [
            ToolMessage(content=load_skill_content("adventure_module"), tool_call_id=tool_call_id)
        ]})

    adventure = _adventure_dict(state)
    node = get_adventure_store().get_node(adventure["active_node_id"])
    payload = {
        "adventure_state": adventure,
        "active_node": {
            "id": node.id,
            "title": node.title,
            "kind": node.kind,
            "source_pages": [node.page_start, node.page_end],
        },
    }
    return Command(update={"messages": [_tool_message(payload, tool_call_id)]})


@tool
def search_adventure_nodes(
    query: str,
    limit: int = 5,
    *,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """搜索 PDF 冒险节点。
    用于玩家偏离当前节点，或提到地点、NPC、线索、遭遇等模组关键词时。
    参数示例：{"query": "克拉摩窝点 洞口", "limit": 5}。

    Args:
        query: 检索词，例如“凡达林 红标帮”“克拉摩窝点”“地精踪迹”。
        limit: 最多返回多少个候选节点。
    """
    results = get_adventure_store().search_nodes(query, limit=max(1, min(limit, 8)))
    payload = {
        "query": query,
        "results": [_node_brief(node, score) for node, score in results],
        "adventure_state": _adventure_dict(state),
    }
    return Command(update={"messages": [_tool_message(payload, tool_call_id)]})


@tool
def switch_adventure_node(
    node_id: str,
    reason: str = "",
    *,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """把当前冒险书签切换到指定节点。
    这是轻量主持书签，不做硬出口校验；只在剧情上合理可达时使用。
    参数示例：{"node_id": "phandalin", "reason": "玩家护送补给抵达凡达林"}。

    Args:
        node_id: 目标节点 ID，通常来自 search_adventure_nodes 或 load_adventure_node。
        reason: 简短说明为什么当前玩家行动可以切换到该节点。
    """
    adventure = _adventure_dict(state)
    current_node_id = adventure["active_node_id"]
    node = get_adventure_store().get_node(node_id)

    if current_node_id and current_node_id not in adventure["completed_node_ids"]:
        adventure["completed_node_ids"].append(current_node_id)
    adventure["active_node_id"] = node.id
    if node.id not in adventure["unlocked_node_ids"]:
        adventure["unlocked_node_ids"].append(node.id)

    payload = _node_payload(node, adventure)
    payload["result"] = {
        "from": current_node_id,
        "to": node.id,
        "reason": reason,
    }
    return Command(update={"adventure": adventure, "messages": [_tool_message(payload, tool_call_id)]})


@tool
def reveal_adventure_clue(
    clue_id: str,
    *,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """记录玩家已经通过调查、审问、搜索或剧情互动获得的线索。
    参数示例：{"clue_id": "goblin_trail"}。

    Args:
        clue_id: 当前节点材料中列出的线索 ID。
    """
    adventure = _adventure_dict(state)
    if clue_id not in adventure["known_clue_ids"]:
        adventure["known_clue_ids"].append(clue_id)

    node = get_adventure_store().get_node(adventure["active_node_id"])
    payload = _node_payload(node, adventure)
    payload["result"] = f"已解锁线索: {clue_id}"
    return Command(update={"adventure": adventure, "messages": [_tool_message(payload, tool_call_id)]})


@tool
def mark_adventure_event(
    event_id: str,
    *,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """记录已经真实发生的剧情事件，例如遭遇解决、NPC 获救或任务完成。
    参数示例：{"event_id": "goblin_ambush_resolved"}。

    Args:
        event_id: 当前节点材料中列出的事件 ID。
    """
    adventure = _adventure_dict(state)
    if event_id not in adventure["completed_event_ids"]:
        adventure["completed_event_ids"].append(event_id)

    payload = {
        "result": f"已记录剧情事件: {event_id}",
        "adventure_state": adventure,
    }
    return Command(update={"adventure": adventure, "messages": [_tool_message(payload, tool_call_id)]})


@tool
def advance_adventure(
    option_id: str,
    *,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """沿当前节点的出口推进到下一个剧情节点。
    只有当出口条件满足时才会改变 active_node_id。
    参数示例：{"option_id": "follow_goblin_trail"}。

    Args:
        option_id: 当前节点 available_exits 中的出口 ID。
    """
    adventure = _adventure_dict(state)
    current_node = get_adventure_store().get_node(adventure["active_node_id"])
    exit_option = next((item for item in current_node.exits if item.id == option_id), None)
    if exit_option is None:
        payload = {
            "error": f"当前节点没有出口: {option_id}",
            "adventure_state": adventure,
        }
        return Command(update={"messages": [_tool_message(payload, tool_call_id)]})

    completed_events = set(adventure["completed_event_ids"])
    known_clues = set(adventure["known_clue_ids"])
    missing = [item for item in exit_option.requires if item not in completed_events and item not in known_clues]
    if missing:
        payload = {
            "error": f"出口条件未满足: {', '.join(missing)}",
            "adventure_state": adventure,
        }
        return Command(update={"messages": [_tool_message(payload, tool_call_id)]})

    if current_node.id not in adventure["completed_node_ids"]:
        adventure["completed_node_ids"].append(current_node.id)
    adventure["active_node_id"] = exit_option.next_node_id
    if exit_option.next_node_id not in adventure["unlocked_node_ids"]:
        adventure["unlocked_node_ids"].append(exit_option.next_node_id)

    next_node = get_adventure_store().get_node(exit_option.next_node_id)
    payload = _node_payload(next_node, adventure)
    payload["result"] = f"已推进剧情: {current_node.id} -> {next_node.id}"
    return Command(update={"adventure": adventure, "messages": [_tool_message(payload, tool_call_id)]})

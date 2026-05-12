"""冒险模组工具 — 让模型按 PDF 节点图读取与推进剧情。"""

from __future__ import annotations

import json
import re
from typing import Any, Annotated, Literal

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from app.adventures.models import AdventureNode, AdventureState
from app.adventures.navigation import apply_arrival_events, normalize_adventure_state, record_node_transition, settle_exit_local_requirements
from app.adventures.rewards import claim_pending_xp_reward, sync_pending_node_rewards
from app.adventures.store import get_adventure_store
from app.services.skills import load_skill_content


SURPRISE_RULE_OVERRIDE = {
    "topic": "surprise",
    "rule": (
        "本项目使用新版突袭规则：模组中“突袭导致第一轮无法行动/无法执行动作”的旧规则不适用。"
        "被突袭者只在开战先攻检定上获得劣势；不跳过首回合，也不因突袭禁用反应。"
    ),
}

SURPRISE_RULE_HINT = (
    "按本项目新版突袭规则处理：该角色被突袭时只在开战先攻检定上获得劣势，"
    "不跳过首回合，也不因突袭禁用反应"
)


def _adventure_dict(state: dict | None) -> dict:
    """读取当前冒险状态；空状态默认从 Lost Mine 初始节点开始。"""
    if not state:
        return AdventureState().model_dump()
    return normalize_adventure_state(state.get("adventure"))


def _normalize_project_rules(value: object) -> object:
    """在不改写源数据的前提下，把旧模组规则转换成本项目可执行口径。"""
    if isinstance(value, str):
        normalized = re.sub(
            r"被突袭且\s*在战斗第一轮无法执行任何动作(?:（见规则书的“突袭”）)?",
            f"被突袭；{SURPRISE_RULE_HINT}",
            value,
        )
        normalized = normalized.replace("见规则书中的突袭规则", "按本项目新版突袭规则处理")
        normalized = normalized.replace("见规则书的“突袭”", "按本项目新版突袭规则处理")
        normalized = normalized.replace("突袭轮", "伏击展开阶段")
        return normalized

    if isinstance(value, list):
        return [_normalize_project_rules(item) for item in value]

    if isinstance(value, dict):
        return {key: _normalize_project_rules(item) for key, item in value.items()}

    return value


def _mentions_surprise(value: object) -> bool:
    """识别需要向模型声明新版突袭覆盖规则的节点材料。"""
    if isinstance(value, str):
        return "突袭" in value
    if isinstance(value, list):
        return any(_mentions_surprise(item) for item in value)
    if isinstance(value, dict):
        return any(_mentions_surprise(item) for item in value.values())
    return False


def _node_payload(node: AdventureNode, adventure: dict) -> dict:
    """返回给模型的节点材料，显式区分玩家可见信息与 DM 私密信息。"""
    store = get_adventure_store()
    completed_events = set(adventure.get("completed_event_ids", []))
    known_clues = set(adventure.get("known_clue_ids", []))
    available_exits = []
    for exit_option in node.exits:
        resolved_next_node_id = store.resolve_node_id(exit_option.next_node_id)
        missing = [item for item in exit_option.requires if item not in completed_events and item not in known_clues]
        available_exits.append(
            {
                "id": exit_option.id,
                "label": exit_option.label,
                "next_node_id": exit_option.next_node_id,
                "resolved_next_node_id": resolved_next_node_id,
                "requires": exit_option.requires,
                "available": not missing and resolved_next_node_id in store._nodes,
                "missing": missing,
                "description": exit_option.description,
                "transition_kind": getattr(exit_option, "transition_kind", "advance"),
            }
        )

    # 中文注释：推进只能看 available_exits；PDF 解析候选出口不是运行时出口，避免模型把空候选误判为无出口。
    node_payload = {
        "id": node.id,
        "title": node.title,
        "kind": node.kind,
        "source_pages": [node.page_start, node.page_end],
        "source_refs": node.source_refs,
        "source_excerpt": node.source_excerpt,
        "source_text": node.source_text,
        "subsections": node.subsections,
        "dm_summary": node.dm_summary,
        "player_visible_intro": node.player_visible_intro,
        "scene_beats": node.scene_beats,
        "npc_reveals": node.npc_reveals,
        "rules_notes": node.rules_notes,
        "fallbacks": node.fallbacks,
        "secrets": node.secrets,
        "checks": node.checks,
        "encounters": [item.model_dump() for item in node.encounters],
        "rewards": node.rewards,
        "clues": node.clues,
        "events": node.events,
        "dm_guidance": node.dm_guidance,
    }
    if node.candidate_exits:
        node_payload["candidate_exits"] = node.candidate_exits

    payload = {
        "node": {
            **node_payload,
        },
        "progression_rule": "剧情推进出口只看顶层 available_exits；available_exits 非空且 available=true 时即可用对应 id 调用 advance。",
        "available_exits": available_exits,
        "adventure_state": adventure,
    }
    if _mentions_surprise(payload["node"]):
        payload["node"]["rules_overrides"] = [SURPRISE_RULE_OVERRIDE]
    return _normalize_project_rules(payload)


def _tool_message(payload: dict, tool_call_id: str | None) -> ToolMessage:
    """冒险工具统一输出 JSON，降低模型误读自然语言的概率。"""
    return ToolMessage(
        content=json.dumps(payload, ensure_ascii=False, indent=2),
        tool_call_id=tool_call_id,
    )


# 冒险工具公共实现：让聚合入口和旧兼容工具共享同一套状态写入。
def _load_adventure_node_impl(node_id: str | None, state: dict | None, tool_call_id: str | None) -> Command:
    adventure = _adventure_dict(state)
    store = get_adventure_store()
    target_node_id = store.resolve_node_id(node_id or adventure["active_node_id"])
    node = store.get_node(target_node_id)
    if target_node_id not in adventure["unlocked_node_ids"]:
        adventure["unlocked_node_ids"].append(target_node_id)

    payload = _node_payload(node, adventure)
    return Command(update={"adventure": adventure, "messages": [_tool_message(payload, tool_call_id)]})


def _inspect_adventure_state_impl(include_help: bool, state: dict | None, tool_call_id: str | None) -> Command:
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


def _search_adventure_nodes_impl(query: str, limit: int, state: dict | None, tool_call_id: str | None) -> Command:
    results = get_adventure_store().search_nodes(query, limit=max(1, min(limit, 8)))
    payload = {
        "query": query,
        "results": [_node_brief(node, score) for node, score in results],
        "adventure_state": _adventure_dict(state),
    }
    return Command(update={"messages": [_tool_message(payload, tool_call_id)]})


def _switch_adventure_node_impl(node_id: str, reason: str, state: dict | None, tool_call_id: str | None) -> Command:
    adventure = _adventure_dict(state)
    current_node_id = adventure["active_node_id"]
    store = get_adventure_store()
    resolved_node_id = store.resolve_node_id(node_id)
    node = store.get_node(resolved_node_id)
    adventure = record_node_transition(
        adventure,
        from_node_id=current_node_id,
        to_node_id=node.id,
        kind="switch",
        reason=reason,
        complete_current=False,
    )

    payload = _node_payload(node, adventure)
    payload["result"] = {"from": current_node_id, "to": node.id, "reason": reason}
    return Command(update={"adventure": adventure, "messages": [_tool_message(payload, tool_call_id)]})


def _reveal_adventure_clue_impl(clue_id: str, state: dict | None, tool_call_id: str | None) -> Command:
    adventure = _adventure_dict(state)
    if clue_id not in adventure["known_clue_ids"]:
        adventure["known_clue_ids"].append(clue_id)

    node = get_adventure_store().get_node(adventure["active_node_id"])
    payload = _node_payload(node, adventure)
    payload["result"] = f"已解锁线索: {clue_id}"
    return Command(update={"adventure": adventure, "messages": [_tool_message(payload, tool_call_id)]})


def _mark_adventure_event_impl(event_id: str, state: dict | None, tool_call_id: str | None) -> Command:
    adventure = _adventure_dict(state)
    node = get_adventure_store().get_node(adventure["active_node_id"])
    if event_id not in node.events:
        payload = {
            "error": f"事件不属于当前节点: {event_id}",
            "allowed_event_ids": node.events,
            "adventure_state": adventure,
        }
        return Command(update={"messages": [_tool_message(payload, tool_call_id)]})
    if event_id not in adventure["completed_event_ids"]:
        adventure["completed_event_ids"].append(event_id)

    payload = {"result": f"已记录剧情事件: {event_id}", "adventure_state": adventure}
    return Command(update={"adventure": adventure, "messages": [_tool_message(payload, tool_call_id)]})


def _resolve_adventure_node_impl(
    outcome: str,
    clue_ids: list[str] | None,
    event_ids: list[str] | None,
    state: dict | None,
    tool_call_id: str | None,
) -> Command:
    """收束当前节点的稳定结果，并把下一步推进选择交还给节点出口。"""
    adventure = _adventure_dict(state)
    node = get_adventure_store().get_node(adventure["active_node_id"])
    allowed_clue_ids = {
        str(item.get("id"))
        for item in node.clues
        if isinstance(item, dict) and item.get("id")
    }
    for clue_id in clue_ids or []:
        if clue_id in allowed_clue_ids and clue_id not in adventure["known_clue_ids"]:
            adventure["known_clue_ids"].append(clue_id)
    for event_id in event_ids or []:
        if event_id in node.events and event_id not in adventure["completed_event_ids"]:
            adventure["completed_event_ids"].append(event_id)

    payload = _node_payload(node, adventure)
    ready_exits = [item for item in payload["available_exits"] if item["available"]]
    payload["result"] = {
        "outcome": outcome,
        "recorded_clue_ids": clue_ids or [],
        "recorded_event_ids": event_ids or [],
    }
    if len(ready_exits) == 1:
        payload["recommended_action"] = {
            "tool": "manage_adventure",
            "args": {"action": "advance", "option_id": ready_exits[0]["id"]},
            "reason": "当前节点只有一个可用出口，收束后应沿该出口完成节点并推进书签。",
        }
    elif len(ready_exits) > 1:
        payload["recommended_action"] = {
            "tool": "ask_player_or_advance_declared_choice",
            "available_option_ids": [item["id"] for item in ready_exits],
            "reason": "当前节点有多个可用出口；若玩家已明确去向，用对应 option_id 推进，否则把选择呈现给玩家。",
        }
    else:
        payload["recommended_action"] = {
            "tool": "continue_current_node",
            "reason": "当前节点暂无满足条件的可用出口，继续围绕本节点主持。",
        }
    return Command(update={"adventure": adventure, "messages": [_tool_message(payload, tool_call_id)]})


def _advance_adventure_impl(option_id: str, state: dict | None, tool_call_id: str | None) -> Command:
    store = get_adventure_store()
    adventure = _adventure_dict(state)
    current_node = store.get_node(adventure["active_node_id"])
    exit_option = next((item for item in current_node.exits if item.id == option_id), None)
    if exit_option is None:
        payload = {
            "error": f"当前节点没有出口: {option_id}",
            "hint": "advance 的 option_id 必须来自 available_exits.id；事件 id 应通过 resolve 的 event_ids 记录。",
            "available_exit_ids": [item.id for item in current_node.exits],
            "current_node_event_ids": current_node.events,
            "adventure_state": adventure,
        }
        return Command(update={"messages": [_tool_message(payload, tool_call_id)]})

    resolved_next_node_id = store.resolve_node_id(exit_option.next_node_id)
    if resolved_next_node_id not in store._nodes:
        payload = {
            "error": f"出口目标节点不存在: {exit_option.next_node_id}",
            "hint": "当前 canonical 节点图里还没有这个落点；请先补齐节点文件或改走其它出口。",
            "available_exit_ids": [item.id for item in current_node.exits],
            "current_node_event_ids": current_node.events,
            "adventure_state": adventure,
        }
        return Command(update={"messages": [_tool_message(payload, tool_call_id)]})

    settle_exit_local_requirements(adventure, current_node, exit_option)

    completed_events = set(adventure["completed_event_ids"])
    known_clues = set(adventure["known_clue_ids"])
    missing = [item for item in exit_option.requires if item not in completed_events and item not in known_clues]
    if missing:
        payload = {"error": f"出口条件未满足: {', '.join(missing)}", "adventure_state": adventure}
        return Command(update={"messages": [_tool_message(payload, tool_call_id)]})

    adventure = record_node_transition(
        adventure,
        from_node_id=current_node.id,
        to_node_id=resolved_next_node_id,
        kind="advance",
        reason=f"advance:{option_id}",
        complete_current=True,
    )

    next_node = store.get_node(resolved_next_node_id)
    apply_arrival_events(adventure, next_node, exit_option_id=exit_option.id)
    sync_pending_node_rewards(adventure, next_node)
    payload = _node_payload(next_node, adventure)
    payload["result"] = f"已推进剧情: {current_node.id} -> {next_node.id}"
    if adventure.get("pending_reward_grants"):
        payload["pending_reward_grants"] = adventure["pending_reward_grants"]
    update: dict[str, Any] = {"adventure": adventure, "messages": [_tool_message(payload, tool_call_id)]}
    return Command(update=update)


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
def manage_adventure(
    action: Literal["help", "load_node", "search_nodes", "switch_node", "resolve", "advance"],
    node_id: str | None = None,
    query: str | None = None,
    limit: int = 5,
    clue_ids: list[str] | None = None,
    event_ids: list[str] | None = None,
    option_id: str | None = None,
    reason: str = "",
    outcome: str = "",
    state: Annotated[dict, InjectedState] = None,
    tool_call_id: Annotated[str, InjectedToolCallId] = None,
) -> Command:
    """统一管理冒险模组节点、线索、事件与剧情书签。
    不确定具体动作时先传 action="help" 读取主持技能说明；涉及剧情事实时优先 load_node；战斗或场景告一段落后用 resolve 收束节点并读取下一步出口。
    参数示例：{"action": "load_node"}；{"action": "search_nodes", "query": "克拉摩窝点 洞口"}；{"action": "resolve", "event_ids": ["goblin_ambush_resolved"], "clue_ids": ["goblin_trail"], "outcome": "伏击已解决"}。

    Args:
        action: 操作类型；help 读取技能说明，load_node 读节点，search_nodes 搜索节点，switch_node 只切换书签不判定完成，resolve 收束当前节点，advance 沿出口推进并完成当前节点。
        node_id: load_node/switch_node 使用的节点 ID。
        query: search_nodes 使用的检索词。
        limit: search_nodes 的结果数量，最多 8。
        clue_ids: resolve 使用的线索 ID 列表。
        event_ids: resolve 使用的事件 ID 列表。
        option_id: advance 使用的出口 ID。
        reason: switch_node 使用的切换原因。
        outcome: resolve 使用的简短节点收束说明。
    """
    if action == "help":
        return _inspect_adventure_state_impl(True, state, tool_call_id)
    if action == "load_node":
        return _load_adventure_node_impl(node_id, state, tool_call_id)
    if action == "search_nodes":
        return _search_adventure_nodes_impl(query or "", limit, state, tool_call_id)
    if action == "switch_node":
        return _switch_adventure_node_impl(node_id or "", reason, state, tool_call_id)
    if action == "resolve":
        return _resolve_adventure_node_impl(outcome, clue_ids, event_ids, state, tool_call_id)
    return _advance_adventure_impl(option_id or "", state, tool_call_id)


@tool
def claim_adventure_reward(
    reward_id: str,
    *,
    state: Annotated[dict, InjectedState] = None,
    tool_call_id: Annotated[str, InjectedToolCallId] = None,
) -> Command:
    """领取后台已判定为待发放的剧情节点奖励，并把奖励内容告知玩家。
    只能使用运行状态帧或冒险工具结果中列出的 pending_reward_grants.id；重复领取同一个 reward_id 不会再次加 XP。
    当前结构化奖励只支持 XP，金币、物品和友谊仍按剧情线索处理。
    成功后要让玩家知道拿到了什么奖励、多少 XP，以及这笔奖励为什么发放。
    参数示例：{"reward_id": "goblin_ambush_hideout_75_xp"}。

    Args:
        reward_id: 待领取剧情奖励 ID，必须来自 pending_reward_grants。
    """
    adventure, player, result = claim_pending_xp_reward(state or {}, reward_id)
    if result.get("ok"):
        reward = result["reward"]
        reward_summary: dict[str, Any] = {
            "ok": True,
            "reward_id": reward["id"],
            "type": reward["type"],
            "amount": reward["amount"],
            "previous_xp": reward["previous_xp"],
            "current_xp": reward["current_xp"],
            "pending_reward_ids": result.get("pending_reward_ids", []),
        }
        if reward.get("description"):
            reward_summary["description"] = reward["description"]
        payload: dict[str, Any] = {
            "tool": "claim_adventure_reward",
            "result": reward_summary,
        }
        description = str(reward.get("description", "")).strip()
        payload["message"] = (
            f"已发放剧情奖励 {reward['id']}: +{reward['amount']} XP，"
            f"当前 XP {reward['current_xp']}。"
            + (description if description else "")
        )
    else:
        # 中文注释：失败时只返回纠错所需字段，避免把完整冒险状态塞回模型上下文。
        payload = {
            "tool": "claim_adventure_reward",
            "result": {
                "ok": False,
                "error": result.get("error", "未知错误"),
                "pending_reward_ids": result.get("pending_reward_ids", []),
                "claimed_reward_ids": result.get("claimed_reward_ids", []),
            },
        }
        payload["message"] = f"剧情奖励未发放：{result.get('error', '未知错误')}"

    update: dict[str, Any] = {"messages": [_tool_message(payload, tool_call_id)]}
    if result.get("ok") or result.get("error", "").startswith("奖励已领取"):
        update["adventure"] = adventure
    if player is not None:
        update["player"] = player
    return Command(update=update)


@tool
def load_adventure_node(
    node_id: str | None = None,
    *,
    state: Annotated[dict, InjectedState] = None,
    tool_call_id: Annotated[str, InjectedToolCallId] = None,
) -> Command:
    """读取当前或指定剧情节点的主持材料。
    用于探索阶段了解当前模组场景、可见开场、DM 私密信息、遭遇、线索和可推进出口。
    参数示例：{} 读取当前节点；{"node_id": "goblin_ambush"} 读取指定节点。

    Args:
        node_id: 可选节点 ID；不传则读取当前 active_node_id。
    """
    return _load_adventure_node_impl(node_id, state, tool_call_id)


@tool
def inspect_adventure_state(
    include_help: bool = False,
    *,
    state: Annotated[dict, InjectedState] = None,
    tool_call_id: Annotated[str, InjectedToolCallId] = None,
) -> Command:
    """查看当前冒险进度；如需完整主持流程说明，传 include_help=True。
    参数示例：{}；加载说明用 {"include_help": true}。
    """
    return _inspect_adventure_state_impl(include_help, state, tool_call_id)


@tool
def search_adventure_nodes(
    query: str,
    limit: int = 5,
    *,
    state: Annotated[dict, InjectedState] = None,
    tool_call_id: Annotated[str, InjectedToolCallId] = None,
) -> Command:
    """搜索 PDF 冒险节点。
    用于玩家偏离当前节点，或提到地点、NPC、线索、遭遇等模组关键词时。
    参数示例：{"query": "克拉摩窝点 洞口", "limit": 5}。

    Args:
        query: 检索词，例如“凡达林 红标帮”“克拉摩窝点”“地精踪迹”。
        limit: 最多返回多少个候选节点。
    """
    return _search_adventure_nodes_impl(query, limit, state, tool_call_id)


@tool
def switch_adventure_node(
    node_id: str,
    reason: str = "",
    *,
    state: Annotated[dict, InjectedState] = None,
    tool_call_id: Annotated[str, InjectedToolCallId] = None,
) -> Command:
    """把当前冒险书签切换到指定节点。
    这是轻量主持书签，不做硬出口校验；只在剧情上合理可达、回访前节点或暂时改线时使用。
    参数示例：{"node_id": "phandalin", "reason": "玩家护送补给抵达凡达林"}。

    Args:
        node_id: 目标节点 ID，通常来自 search_adventure_nodes 或 load_adventure_node。
        reason: 简短说明为什么当前玩家行动可以切换到该节点。
    """
    return _switch_adventure_node_impl(node_id, reason, state, tool_call_id)


@tool
def reveal_adventure_clue(
    clue_id: str,
    *,
    state: Annotated[dict, InjectedState] = None,
    tool_call_id: Annotated[str, InjectedToolCallId] = None,
) -> Command:
    """记录玩家已经通过调查、审问、搜索或剧情互动获得的线索。
    参数示例：{"clue_id": "goblin_trail"}。

    Args:
        clue_id: 当前节点材料中列出的线索 ID。
    """
    return _reveal_adventure_clue_impl(clue_id, state, tool_call_id)


@tool
def mark_adventure_event(
    event_id: str,
    *,
    state: Annotated[dict, InjectedState] = None,
    tool_call_id: Annotated[str, InjectedToolCallId] = None,
) -> Command:
    """记录已经真实发生的剧情事件，例如遭遇解决、NPC 获救或任务完成。
    参数示例：{"event_id": "goblin_ambush_resolved"}。

    Args:
        event_id: 当前节点材料中列出的事件 ID。
    """
    return _mark_adventure_event_impl(event_id, state, tool_call_id)


@tool
def advance_adventure(
    option_id: str,
    *,
    state: Annotated[dict, InjectedState] = None,
    tool_call_id: Annotated[str, InjectedToolCallId] = None,
) -> Command:
    """沿当前节点的出口推进到下一个剧情节点。
    只有当出口条件满足时才会改变 active_node_id，并把当前节点标记为已完成。
    参数示例：{"option_id": "follow_goblin_trail"}。

    Args:
        option_id: 当前节点 available_exits 中的出口 ID。
    """
    return _advance_adventure_impl(option_id, state, tool_call_id)

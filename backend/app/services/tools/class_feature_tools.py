"""职业特性工具入口。"""

from __future__ import annotations

from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from app.services.class_features import FeatureContext, FeatureTrigger, available_features, run_feature
from app.services.tools._helpers import get_combatant, get_player_identity, is_player_reference


def _state_value_to_dict(value) -> dict | None:
    """统一把 LangGraph/Pydantic 状态值转成普通字典。"""
    if not value:
        return None
    return value.model_dump() if hasattr(value, "model_dump") else dict(value)


def _mapping_state_to_dict(value) -> dict:
    """统一处理 scene_units 这类映射状态。"""
    if not value:
        return {}
    if hasattr(value, "items"):
        return {k: v.model_dump() if hasattr(v, "model_dump") else dict(v) for k, v in value.items()}
    return {}


def _resolve_feature_target(state: dict, player_dict: dict, target_id: str) -> tuple[dict | None, str, dict]:
    """按玩家、战斗单位、场景单位顺序解析职业特性目标。"""
    update: dict = {}
    if not target_id:
        return None, "", update
    if is_player_reference(player_dict, target_id):
        return player_dict, "player", update

    combat_dict = _state_value_to_dict(state.get("combat"))
    if combat_dict:
        target = get_combatant(combat_dict, player_dict, target_id)
        if target:
            update["combat"] = combat_dict
            return target, "combat", update

    scene_units = _mapping_state_to_dict(state.get("scene_units"))
    if target_id in scene_units:
        update["scene_units"] = scene_units
        return scene_units[target_id], "scene", update

    return None, "", update


@tool
def use_class_feature(
    feature_id: str = "",
    trigger: FeatureTrigger = "active_use",
    target_id: str = "",
    payload: dict | None = None,
    state: Annotated[dict, InjectedState] = None,
    tool_call_id: Annotated[str, InjectedToolCallId] = None,
) -> Command:
    """使用当前玩家的职业特性；feature_id 为空时列出指定触发点可用特性。"""
    player_dict = _state_value_to_dict(state.get("player"))
    if not player_dict:
        return Command(update={"messages": [
            ToolMessage(content="玩家尚未加载角色卡。", tool_call_id=tool_call_id)
        ]})

    actor_id, actor_name = get_player_identity(player_dict)
    player_dict["id"] = actor_id
    player_dict["name"] = actor_name

    usable = available_features(player_dict, trigger)
    if not feature_id:
        content = (
            f"[职业特性] {actor_name} 在触发点 {trigger} 可用: {', '.join(usable) or '无'}。"
        )
        return Command(update={"player": player_dict, "messages": [
            ToolMessage(content=content, tool_call_id=tool_call_id)
        ]})

    if feature_id not in player_dict.get("class_features", []):
        return Command(update={"messages": [
            ToolMessage(content=f"{actor_name} 没有职业特性: {feature_id}。", tool_call_id=tool_call_id)
        ]})

    target, target_source, base_update = _resolve_feature_target(state, player_dict, target_id)
    try:
        result = run_feature(
            feature_id,
            trigger,
            FeatureContext(
                actor=player_dict,
                target=target,
                state=state,
                payload=payload or {},
            ),
        )
    except KeyError:
        content = (
            f"职业特性 {feature_id} 尚未实现触发点 {trigger}。"
            f"当前该触发点可用: {', '.join(usable) or '无'}。"
        )
        return Command(update={"messages": [ToolMessage(content=content, tool_call_id=tool_call_id)]})

    update = {**base_update, **result.update}
    update["player"] = player_dict
    if target_source == "combat" and target_id and "combat" in update:
        update["combat"]["participants"][target_id] = target
    elif target_source == "scene" and target_id and "scene_units" in update:
        update["scene_units"][target_id] = target

    update["messages"] = [ToolMessage(content="\n".join(result.lines), tool_call_id=tool_call_id)]
    return Command(update=update)

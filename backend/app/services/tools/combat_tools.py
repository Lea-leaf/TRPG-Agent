"""战斗工具链 — 生成怪物、开始/结束战斗、攻击、回合推进"""

from __future__ import annotations

from typing import Annotated, Literal

import d20
from langchain_core.messages import BaseMessage, ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from app.allies.profiles import get_ally_profile
from app.calculation.bestiary import spawn_combatants
from app.services.skills import load_skill_content
from app.space.geometry import build_space_state
from app.space.geometry import validate_unit_distance as validate_space_unit_distance
from app.services.tools._helpers import (
    advance_turn,
    apply_hp_change,
    apply_attack_damage,
    build_attack_roll_event_payload,
    build_pending_reaction_state,
    canonical_combatant_id,
    canonicalize_player_space,
    clear_player_combat_fields,
    choose_attack,
    available_attack_names,
    get_all_combatants,
    get_combatant,
    prepare_player_for_combat,
    prepare_character_for_combat,
    roll_attack_hit,
    tracks_death_saves,
    validate_attack_distance,
)
from app.services.tools.reactions import get_available_reactions
from app.services.tools.spell_tools import apply_automatic_hit_reaction


def _message_count(state: dict | None) -> int:
    messages = state.get("messages") or [] if state else []
    return len(messages)


def _combat_archive_start_index(state: dict | None) -> int:
    """战斗归档从触发 start_combat 的 AIMessage 开始，保证 tool_calls 与 ToolMessage 同生共死。"""
    messages = state.get("messages") or [] if state else []
    if messages and getattr(messages[-1], "tool_calls", None):
        return len(messages) - 1
    return len(messages)


def _combat_archives_from_state(state: dict | None) -> list[dict]:
    if not state:
        return []

    raw_archives = state.get("combat_archives") or []
    archives: list[dict] = []
    for archive in raw_archives:
        if hasattr(archive, "model_dump"):
            archives.append(archive.model_dump())
        elif hasattr(archive, "items"):
            archives.append(dict(archive))
    return archives


def _build_combat_archive(summary: str, start_index: int, end_index: int) -> dict:
    """归档只保留区间锚点与高密度摘要，供后续 prompt 折叠使用。"""
    safe_start = max(start_index, 0)
    safe_end = max(end_index, safe_start)
    return {
        "summary": summary.strip(),
        "start_index": safe_start,
        "end_index": safe_end,
    }


def _build_detailed_combat_archive_summary(base_summary: str, state: dict | None, start_index: int) -> str:
    """战斗归档要保留足够经过，否则战后模型容易把已完成战斗误判成待执行任务。"""
    messages = state.get("messages") or [] if state else []
    if not messages or start_index >= len(messages):
        return base_summary

    raw_lines: list[str] = []
    for message in messages[max(start_index, 0):]:
        line = _archive_message_line(message)
        if line:
            raw_lines.append(line)
    if not raw_lines:
        return base_summary

    raw_text = "\n".join(raw_lines)
    detail_budget = max(1200, int(len(raw_text) * 0.3))
    detail_text = _compact_archive_text(raw_text, detail_budget)
    return (
        f"{base_summary}\n"
        "关键经过（已发生事实，约按原战斗记录三成以上预算保留）："
        f"{detail_text}"
    )


def _archive_message_line(message: BaseMessage) -> str:
    """把战斗区间内的消息转成归档文本，保留工具结果而不是只留最终一句。"""
    tool_calls = getattr(message, "tool_calls", None) or []
    content = _message_content_to_text(getattr(message, "content", "")).strip()
    if tool_calls:
        tool_names = ", ".join(str(tool_call.get("name", "")) for tool_call in tool_calls)
        return f"工具调用: {tool_names}" + (f" | {content}" if content else "")
    if isinstance(message, ToolMessage):
        tool_name = getattr(message, "name", "") or "tool"
        return f"工具结果[{tool_name}]: {content}"
    return content


def _message_content_to_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("text"):
                parts.append(str(item["text"]))
        return "\n".join(parts)
    return str(content)


def _compact_archive_text(text: str, limit: int) -> str:
    """归档压缩只清理空白与硬截断，不改写事实以免制造新剧情。"""
    compact = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if len(compact) > limit:
        return compact[: limit - 3].rstrip() + "..."
    return compact


def _remove_space_units(space_raw: dict | None, unit_ids: list[str]) -> dict | None:
    """战斗收尾时把尸体从空间落点里真正移除，避免地图上只剩“摆角落”的假清理。"""
    if not space_raw:
        return None

    space = build_space_state(space_raw)
    for unit_id in unit_ids:
        space.placements.pop(unit_id, None)
    return space.model_dump()


def _validate_combat_space(state: dict, unit_ids: list[str]) -> str | None:
    """战斗必须绑定客观地图，否则距离、移动和范围规则会失去事实来源。"""
    space = build_space_state(state.get("space"))
    if not space.maps or not space.active_map_id or space.active_map_id not in space.maps:
        return "无法开始战斗：当前没有可用平面地图。请先用 manage_space 创建或切换地图，并放置参战单位。"

    missing = [unit_id for unit_id in unit_ids if unit_id not in space.placements]
    if missing:
        return f"无法开始战斗：以下参战单位尚未放置到当前平面地图: {', '.join(missing)}。请先用 manage_space 放置单位。"

    wrong_map = [unit_id for unit_id in unit_ids if space.placements[unit_id].map_id != space.active_map_id]
    if wrong_map:
        active_map = space.maps[space.active_map_id]
        return f"无法开始战斗：以下参战单位不在当前地图 {active_map.name} [ID:{space.active_map_id}]: {', '.join(wrong_map)}。请先切换地图或重新放置单位。"

    return None


def _resolve_surprised_ids(raw_ids: list[str], all_units: dict[str, dict], player_dict: dict | None) -> tuple[set[str], list[str]]:
    """新版突袭只标记先攻劣势目标，避免再引入跳过回合的旧状态。"""
    surprised: set[str] = set()
    missing: list[str] = []
    for raw_id in raw_ids:
        unit_id = str(raw_id).strip()
        if player_dict and unit_id in {"player", "玩家", "当前玩家"}:
            unit_id = player_dict["id"]
        if unit_id in all_units:
            surprised.add(unit_id)
        else:
            missing.append(str(raw_id))
    return surprised, missing


def _roll_initiative(unit: dict, *, surprised: bool) -> tuple[int, str]:
    """先攻骰统一入口；新版突袭让目标先攻劣势，而不是失去首回合。"""
    dex_mod = unit.get("modifiers", {}).get("dex", 0)
    expr = f"2d20kl1+{dex_mod}" if surprised else f"1d20+{dex_mod}"
    result = d20.roll(expr)
    return result.total, str(result)


# 场景单位公共实现：聚合入口和旧工具共用，避免两套生成/清理逻辑漂移。
def _spawn_ally_impl(
    profile_id: str,
    name: str | None,
    unit_id: str | None,
    state: dict | None,
    tool_call_id: str | None,
) -> Command:
    try:
        ally = get_ally_profile(profile_id)
    except ValueError as exc:
        return Command(update={"messages": [ToolMessage(content=str(exc), tool_call_id=tool_call_id)]})

    if name:
        ally["name"] = name
    ally["id"] = unit_id or ally.get("id") or profile_id
    ally["side"] = "ally"
    prepare_character_for_combat(ally, side="ally", fallback_id=ally["id"])

    scene_units: dict = state.get("scene_units") or {} if state else {}
    scene_raw = {k: v.model_dump() if hasattr(v, "model_dump") else dict(v) for k, v in scene_units.items()} if hasattr(scene_units, "items") else {}
    scene_raw[ally["id"]] = ally

    return Command(update={
        "scene_units": scene_raw,
        "messages": [
            ToolMessage(content=f"友方 {ally['name']} [ID: {ally['id']}] 已加入场景。", tool_call_id=tool_call_id)
        ],
    })


def _spawn_monsters_impl(
    monster_index: str,
    count: int,
    faction: str,
    state: dict | None,
    tool_call_id: str | None,
) -> Command:
    try:
        new_combatants = spawn_combatants(monster_index, count, faction)
    except Exception as exc:
        return Command(update={"messages": [ToolMessage(content=f"生成战斗单位失败: {exc}", tool_call_id=tool_call_id)]})

    scene_units: dict = state.get("scene_units") or {} if state else {}
    scene_raw = {k: v.model_dump() if hasattr(v, "model_dump") else dict(v) for k, v in scene_units.items()} if hasattr(scene_units, "items") else {}

    for combatant in new_combatants:
        scene_raw[combatant.id] = combatant.model_dump()

    names = [f"{combatant.name} [ID: {combatant.id}]" for combatant in new_combatants]
    return Command(update={
        "scene_units": scene_raw,
        "messages": [
            ToolMessage(
                content=(
                    f"成功在场景中生成了 {count} 只 {monster_index}: {', '.join(names)}。\n"
                    "可用 start_combat 指定哪些单位参加战斗。"
                ),
                tool_call_id=tool_call_id,
            )
        ],
    })


def _clear_dead_units_impl(unit_ids: list[str] | None, state: dict | None, tool_call_id: str | None) -> Command:
    dead_units: dict = state.get("dead_units") or {} if state else {}
    dead_raw = {k: v.model_dump() if hasattr(v, "model_dump") else dict(v) for k, v in dead_units.items()} if hasattr(dead_units, "items") else {}

    if not dead_raw:
        return Command(update={"messages": [ToolMessage(content="当前没有死亡单位。", tool_call_id=tool_call_id)]})

    if unit_ids:
        removed = [uid for uid in unit_ids if uid in dead_raw]
        for uid in removed:
            del dead_raw[uid]
        msg = f"已清除死亡单位: {', '.join(removed)}" if removed else "指定的 ID 不在死亡单位列表中。"
    else:
        count = len(dead_raw)
        dead_raw.clear()
        msg = f"已清除全部 {count} 个死亡单位。"

    return Command(update={"dead_units": dead_raw, "messages": [ToolMessage(content=msg, tool_call_id=tool_call_id)]})


@tool
def manage_scene_units(
    action: Literal["help", "spawn_ally", "spawn_monsters", "clear_dead_units"],
    profile_id: str | None = None,
    name: str | None = None,
    unit_id: str | None = None,
    monster_index: str | None = None,
    count: int = 1,
    faction: str = "enemy",
    unit_ids: list[str] | None = None,
    state: Annotated[dict, InjectedState] = None,
    tool_call_id: Annotated[str, InjectedToolCallId] = None,
) -> Command:
    """统一管理场景单位池中的友方、怪物与死亡单位档案。
    不确定模板、怪物 slug 或清理时机时先传 action="help" 读取场景单位技能说明。
    参数示例：{"action": "spawn_ally", "profile_id": "fighter_companion"}；{"action": "spawn_monsters", "monster_index": "goblin", "count": 4}。

    Args:
        action: help 读取说明，spawn_ally 创建友方，spawn_monsters 创建怪物，clear_dead_units 清理死亡档案。
        profile_id: 友方模板 ID，例如 fighter_companion、apprentice_wizard。
        name: 可选友方显示名。
        unit_id: 可选友方单位 ID。
        monster_index: 怪物 Open5e slug，例如 goblin、wolf、bugbear。
        count: 创建怪物数量。
        faction: 怪物阵营，通常为 enemy、ally 或 neutral。
        unit_ids: clear_dead_units 指定清理的死亡单位 ID；不传则清理全部。
    """
    if action == "help":
        return Command(update={"messages": [
            ToolMessage(content=load_skill_content("scene_unit_management"), tool_call_id=tool_call_id)
        ]})
    if action == "spawn_ally":
        return _spawn_ally_impl(profile_id or "", name, unit_id, state, tool_call_id)
    if action == "spawn_monsters":
        return _spawn_monsters_impl(monster_index or "", count, faction, state, tool_call_id)
    return _clear_dead_units_impl(unit_ids, state, tool_call_id)


@tool
def spawn_ally(
    profile_id: str,
    name: str | None = None,
    unit_id: str | None = None,
    state: Annotated[dict, InjectedState] = None,
    tool_call_id: Annotated[str, InjectedToolCallId] = None,
) -> Command:
    """根据友方角色模板生成受 Agent 控制的友方单位，并加入场景单位池。
    友方使用角色型规则：武器、法术位、已知法术、职业特性与反应资源都写在单位状态里。
    参数示例：{"profile_id": "apprentice_wizard", "name": "伊莲"}。

    Args:
        profile_id: 友方模板 ID，例如 "sildar"、"apprentice_wizard"、"acolyte_healer"。
        name: 可选显示名；不传则使用模板默认名。
        unit_id: 可选单位 ID；不传则按模板 ID 自动生成稳定 ID。
    """
    return _spawn_ally_impl(profile_id, name, unit_id, state, tool_call_id)


@tool
def spawn_monsters(
    monster_index: str,
    count: int = 1,
    faction: str = "enemy",
    *,
    state: Annotated[dict, InjectedState] = None,
    tool_call_id: Annotated[str, InjectedToolCallId] = None
) -> Command:
    """根据怪物图鉴生成战斗单位实例并加入当前场景。
    怪物数据来自 Open5e SRD（使用英文 slug，如 "goblin", "owlbear", "adult-red-dragon"）。
    生成后的单位进入场景单位池（scene_units），需要通过 start_combat 指定参战。
    参数示例：{"monster_index": "goblin", "count": 4, "faction": "enemy"}。

    Args:
        monster_index: 怪物的 Open5e slug，必须是英文代号，例如 "goblin"、"wolf"、"bugbear"。
        count: 生成该单位的数量，例如 4。
        faction: 阵营，通常为 "enemy"、"ally" 或 "neutral"。
    """
    return _spawn_monsters_impl(monster_index, count, faction, state, tool_call_id)


@tool
def help_action(
    actor_id: str,
    target_id: str,
    state: Annotated[dict, InjectedState] = None,
    tool_call_id: Annotated[str, InjectedToolCallId] = None,
) -> Command:
    """执行援助动作。当前接入桌面规则中的急救稳定：对 0 HP 生物进行 DC 10 WIS(Medicine) 检定。
    成功会让目标稳定在 0 HP，不恢复 HP；要让目标重新站起来仍需治疗或复活类状态调整。
    参数示例：{"actor_id": "fighter_companion", "target_id": "温良"}。

    Args:
        actor_id: 执行援助的单位 ID，必须是当前回合行动者。
        target_id: 要急救稳定的 0 HP 单位 ID。
    """
    combat_raw = state.get("combat")
    if not combat_raw:
        return Command(update={"messages": [ToolMessage(content="[援助失败] 当前不在战斗中。", tool_call_id=tool_call_id)]})

    combat_dict = combat_raw.model_dump() if hasattr(combat_raw, "model_dump") else dict(combat_raw)
    player_raw = state.get("player")
    player_dict = player_raw.model_dump() if hasattr(player_raw, "model_dump") else dict(player_raw) if player_raw else None

    actor = get_combatant(combat_dict, player_dict, actor_id)
    target = get_combatant(combat_dict, player_dict, target_id)
    resolved_actor_id = canonical_combatant_id(actor, actor_id)
    resolved_target_id = canonical_combatant_id(target, target_id)

    def _reject(msg: str) -> Command:
        return Command(update={"messages": [ToolMessage(content=f"[援助失败] {msg}", tool_call_id=tool_call_id)]})

    if not actor:
        return _reject(f"找不到行动者 '{actor_id}'。")
    if not target:
        return _reject(f"找不到目标 '{target_id}'。")
    if combat_dict.get("current_actor_id") != resolved_actor_id:
        return _reject(f"现在不是 {actor.get('name', actor_id)} 的回合，当前行动者为 {combat_dict.get('current_actor_id')}。")
    if actor.get("hp", 0) <= 0:
        return _reject(f"{actor.get('name', actor_id)} 已经倒下，无法执行援助。")
    if not actor.get("action_available", True):
        return _reject(f"{actor.get('name', actor_id)} 本回合的动作已用尽。")
    if target.get("hp", 0) > 0:
        return _reject(f"{target.get('name', target_id)} 仍有 HP，不需要急救稳定。")
    if target.get("is_dead"):
        return _reject(f"{target.get('name', target_id)} 已死亡，急救无法稳定；需要复活类能力。")
    if target.get("is_stable"):
        return _reject(f"{target.get('name', target_id)} 已经伤势稳定。")
    if distance_error := validate_space_unit_distance(
        state.get("space"),
        resolved_actor_id,
        resolved_target_id,
        5,
        action_label="援助急救",
    ):
        return _reject(distance_error)

    wis_mod = int(actor.get("modifiers", {}).get("wis", 0) or 0)
    prof = int(actor.get("proficiency_bonus", 2) or 2)
    proficient = "medicine" in {str(item).lower() for item in actor.get("skill_proficiencies", [])}
    bonus = wis_mod + (prof if proficient else 0)
    result = d20.roll(f"1d20{bonus:+d}")
    actor["action_available"] = False

    lines = [
        f"{actor.get('name', actor_id)} 使用援助动作急救 {target.get('name', target_id)}。",
        f"WIS(Medicine) DC 10: {result}（{'含熟练' if proficient else '无熟练'}）",
    ]
    if result.total >= 10:
        target["hp"] = 0
        target["death_save_successes"] = 0
        target["death_save_failures"] = 0
        target["is_stable"] = True
        target["is_dead"] = False
        lines.append(f"{target.get('name', target_id)} 伤势稳定，保持 0 HP。")
    else:
        lines.append(f"{target.get('name', target_id)} 未能稳定，死亡豁免状态不变。")

    update: dict = {
        "combat": combat_dict,
        "messages": [ToolMessage(content="\n".join(lines), tool_call_id=tool_call_id)],
    }
    if player_dict:
        update["player"] = player_dict
    return Command(update=update)


@tool
def start_combat(
    combatant_ids: list[str],
    surprised_ids: list[str] | None = None,
    *,
    state: Annotated[dict, InjectedState] = None,
    tool_call_id: Annotated[str, InjectedToolCallId] = None,
) -> Command:
    """开始战斗：从场景单位池中选取指定 ID 的单位作为参战者，投先攻骰并排定行动顺序。
    前置条件：必须先用 spawn_monsters 生成单位，并用 manage_space 把玩家和参战单位放到当前地图。
    玩家角色会自动加入，无需在 combatant_ids 中指定；友方不是玩家，必须和敌人一样显式列入 combatant_ids。
    新版突袭只让被突袭者先攻劣势，不跳过首回合，也不禁用反应。
    开战前若需要判断突袭/被突袭，先对玩家小队或敌方小队整体做一次感知/潜行对抗，不要为每个单位逐个掷骰；判定完成后把被突袭单位 ID 放入 surprised_ids。
    参数示例：{"combatant_ids": ["fighter_companion", "goblin_1", "goblin_2"], "surprised_ids": ["player"]}。

    Args:
        combatant_ids: 从场景单位池中参加本次战斗的非玩家单位 ID 列表；敌人和友方都要放进来，不要把玩家 ID 放进来。
        surprised_ids: 被突袭的单位 ID；这些单位先攻检定用劣势。可用 "player" 指代当前玩家。
    """
    scene_units: dict = state.get("scene_units") or {}
    if hasattr(scene_units, "items"):
        scene_raw = {k: v.model_dump() if hasattr(v, "model_dump") else dict(v) for k, v in scene_units.items()}
    else:
        scene_raw = {}

    if not combatant_ids and not scene_raw:
        return "场景中没有任何单位。请先使用 spawn_monsters 或 spawn_ally 生成参战单位。"

    participants: dict[str, dict] = {}
    missing: list[str] = []
    for uid in combatant_ids:
        unit = scene_raw.get(uid)
        if unit:
            participants[uid] = unit
        else:
            missing.append(uid)

    if missing:
        available = ", ".join(scene_raw.keys()) or "无"
        return f"找不到以下单位: {', '.join(missing)}。场景中可用单位: {available}"

    # 玩家自动入场 — 直接在 player_dict 上叠加战斗字段，不再复制到 participants
    player_raw = state.get("player")
    player_dict: dict | None = None
    if player_raw:
        player_dict = player_raw.model_dump() if hasattr(player_raw, "model_dump") else dict(player_raw)
        prepare_player_for_combat(player_dict)

    if not participants and not player_dict:
        return "没有参战者，请先生成怪物或加载角色卡。"

    for uid, unit in list(participants.items()):
        if unit.get("side") == "ally" or unit.get("unit_kind") == "character":
            prepare_character_for_combat(unit, side=unit.get("side", "ally"), fallback_id=uid)
            participants[uid] = unit

    # 为所有参战单位投先攻（含玩家）
    all_units: dict[str, dict] = dict(participants)
    if player_dict:
        all_units[player_dict["id"]] = player_dict

    state = {**state, "space": canonicalize_player_space(state.get("space"), player_dict)}
    if space_error := _validate_combat_space(state, list(all_units)):
        return Command(update={"messages": [ToolMessage(content=space_error, tool_call_id=tool_call_id)]})

    surprised_set, surprise_missing = _resolve_surprised_ids(surprised_ids or [], all_units, player_dict)
    if surprise_missing:
        available = ", ".join(all_units.keys()) or "无"
        return Command(update={"messages": [
            ToolMessage(
                content=f"无法开始战斗：找不到被突袭单位 {', '.join(surprise_missing)}。可用单位: {available}",
                tool_call_id=tool_call_id,
            )
        ]})

    initiative_list: list[tuple[str, int, str, bool]] = []
    for uid, p in all_units.items():
        surprised = uid in surprised_set
        init_total, roll_text = _roll_initiative(p, surprised=surprised)
        p["initiative"] = init_total
        p["surprised"] = surprised
        initiative_list.append((uid, init_total, roll_text, surprised))

    initiative_list.sort(key=lambda x: x[1], reverse=True)
    order = [uid for uid, _, _, _ in initiative_list]

    # combat.participants 仅存 NPC/怪物
    combat_dict = {
        "round": 1,
        "participants": participants,
        "initiative_order": order,
        "current_actor_id": order[0],
    }

    order_desc = "\n".join(
        f"  {i+1}. {all_units[uid].get('name', uid)} [ID: {uid}] "
        f"(先攻 {init}{'，突袭劣势' if surprised else ''}；{roll_text})"
        for i, (uid, init, roll_text, surprised) in enumerate(initiative_list)
    )

    update: dict = {
        "combat": combat_dict,
        "phase": "combat",
        "active_combat_message_start": _combat_archive_start_index(state),
        "messages": [
            ToolMessage(
                content=(
                    "战斗开始！第 1 回合。\n"
                    "先攻已经由工具完成结算；突袭单位的先攻劣势已计入下列骰式。"
                    "必须以此先攻顺序和当前行动者为准，不要自行重排或补骰。\n"
                    f"先攻顺序：\n{order_desc}\n\n"
                    f"当前行动者：{all_units[order[0]].get('name', order[0])} [ID: {order[0]}]"
                ),
                tool_call_id=tool_call_id,
            )
        ],
    }
    if player_dict:
        update["player"] = player_dict

    return Command(update=update)


@tool
def attack_action(
    attacker_id: str,
    target_id: str,
    attack_name: str | None = None,
    advantage: Literal["normal", "advantage", "disadvantage"] = "normal",
    *,
    state: Annotated[dict, InjectedState] = None,
    tool_call_id: Annotated[str, InjectedToolCallId] = None,
) -> Command:
    """执行一次攻击动作：命中判定 → 暴击检测 → 伤害结算 → 扣血。
    状态效果（如目盲、隐形等）的优劣势会自动叠加计算。
    玩家攻击结束后如果没有其他额外动作，可以询问玩家或代表玩家调用 `next_turn`。
    参数示例：{"attacker_id": "温良", "target_id": "goblin_1", "attack_name": "Longsword", "advantage": "normal"}。

    Args:
        attacker_id: 攻击者 ID，必须是当前回合行动者。
        target_id: 目标单位 ID。
        attack_name: 使用的攻击名称或动作名；不确定时可省略，让工具使用第一个攻击方式。
        advantage: 攻击优劣势，只能是 "normal"、"advantage" 或 "disadvantage"。
    """
    combat_raw = state.get("combat")
    if not combat_raw:
        return "当前不在战斗中。"

    combat_dict = combat_raw.model_dump() if hasattr(combat_raw, "model_dump") else dict(combat_raw)

    # 获取玩家字典（如有）
    player_raw = state.get("player")
    player_dict = player_raw.model_dump() if hasattr(player_raw, "model_dump") else dict(player_raw) if player_raw else None

    # 通过统一接口获取攻防双方
    attacker = get_combatant(combat_dict, player_dict, attacker_id)
    target = get_combatant(combat_dict, player_dict, target_id)
    resolved_attacker_id = canonical_combatant_id(attacker, attacker_id)
    resolved_target_id = canonical_combatant_id(target, target_id)

    def _reject(msg: str) -> Command:
        return Command(update={"messages": [
            ToolMessage(content=f"[攻击失败] {msg}", tool_call_id=tool_call_id)
        ]})

    if not attacker:
        return _reject(f"找不到攻击者 '{attacker_id}'。")
    if not target:
        return _reject(f"找不到目标 '{target_id}'。")
    if combat_dict.get("current_actor_id") != resolved_attacker_id:
        return _reject(f"现在不是 {attacker.get('name', attacker_id)} 的回合，当前行动者为 {combat_dict.get('current_actor_id')}。")
    if attacker.get("hp", 0) <= 0:
        return _reject(f"{attacker.get('name', attacker_id)} 已经倒下，无法攻击；若这是玩家回合，应先进行死亡豁免。")
    if target.get("hp", 0) <= 0 and not tracks_death_saves(target):
        return _reject(f"目标 {target.get('name', target_id)} 已经倒下，无法攻击。")
    if not attacker.get("action_available", True):
        return _reject(f"{attacker.get('name', attacker_id)} 本回合的动作已用尽。")

    chosen_attack = choose_attack(attacker, attack_name)
    if attack_name and chosen_attack is None:
        available = ", ".join(available_attack_names(attacker)) or "无"
        return _reject(f"未知攻击 '{attack_name}'。可用攻击: {available}。")
    canonical_space = canonicalize_player_space(state.get("space"), player_dict)
    if distance_error := validate_attack_distance(canonical_space, resolved_attacker_id, resolved_target_id, chosen_attack):
        return _reject(distance_error)

    roll_info = roll_attack_hit(attacker, target, attack_name, advantage, state)
    auto_reaction_lines = apply_automatic_hit_reaction(target, attacker, roll_info, state)

    if (
        player_dict
        and attacker.get("side") != "player"
        and target is player_dict
        and roll_info.get("hit")
        and not roll_info.get("blocked")
    ):
        reaction_context = {
            "attacker": attacker.get("name", attacker_id),
            "attack_roll": {
                "raw_roll": roll_info.get("raw_roll", roll_info.get("natural", 0)),
                "attack_bonus": roll_info.get("attack_bonus", 0),
                "final_total": roll_info.get("hit_total", 0),
                "hit_total": roll_info.get("hit_total", 0),
                "target_ac": roll_info.get("target_ac", 10),
            },
        }
        available_reactions = get_available_reactions(player_dict, "on_hit", reaction_context)
        if available_reactions:
            pending_reaction_msg = ToolMessage(
                content=(
                    f"{attacker.get('name', attacker_id)} 的攻击命中了 {target.get('name', target_id)}，"
                    "已进入反应判定，等待玩家选择。"
                ),
                tool_call_id=tool_call_id,
                additional_kwargs={"hidden_from_ui": True},
            )
            return Command(
                update={
                    "combat": combat_dict,
                    "player": player_dict,
                    "messages": [pending_reaction_msg],
                    "pending_reaction": build_pending_reaction_state(attacker, target, roll_info, available_reactions),
                    "reaction_choice": None,
                }
            )

    lines, _, hp_change, _ = apply_attack_damage(attacker, target, roll_info)
    lines = auto_reaction_lines + lines

    attack_roll_payload = build_attack_roll_event_payload(roll_info)

    tool_message_kwargs = {}
    if attack_roll_payload:
        tool_message_kwargs["additional_kwargs"] = {"attack_roll": attack_roll_payload}

    tool_msg = ToolMessage(
        content="\n".join(lines),
        tool_call_id=tool_call_id,
        **tool_message_kwargs,
    )

    # 玩家数据已在 player_dict 上原地修改，无需手动同步
    update: dict = {
        "combat": combat_dict,
        "messages": [tool_msg],
    }
    if player_dict:
        update["player"] = player_dict
    if hp_change:
        update["hp_changes"] = [hp_change]

    return Command(update=update)


@tool
def next_turn(
    *,
    state: Annotated[dict, InjectedState] = None,
    tool_call_id: Annotated[str, InjectedToolCallId] = None,
) -> Command:
    """结束当前行动者回合，并推进到下一个存活单位。如果所有人都行动过，则进入新的回合。
    参数示例：{}。
    """
    combat_raw = state.get("combat")
    if not combat_raw:
        return "当前不在战斗中。"

    combat_dict = combat_raw.model_dump() if hasattr(combat_raw, "model_dump") else dict(combat_raw)

    player_raw = state.get("player")
    player_dict = player_raw.model_dump() if hasattr(player_raw, "model_dump") else dict(player_raw) if player_raw else None

    if not combat_dict.get("initiative_order"):
        return "先攻顺序为空，请先调用 start_combat。"

    result_text = advance_turn(combat_dict, player_dict, state)

    update: dict = {
        "combat": combat_dict,
        "messages": [
            ToolMessage(content=result_text, tool_call_id=tool_call_id)
        ],
    }
    if player_dict:
        update["player"] = player_dict

    return Command(update=update)


@tool
def end_combat(
    *,
    state: Annotated[dict, InjectedState] = None,
    tool_call_id: Annotated[str, InjectedToolCallId] = None,
) -> Command:
    """结束当前战斗。存活的非玩家单位回归场景，死亡单位归入死亡档案（可搜尸等）。
    参数示例：{}。
    """
    combat_raw = state.get("combat")
    summary = "战斗结束。"
    update: dict = {
        "combat": None,
        "phase": "exploration",
        "active_combat_message_start": None,
    }

    player_raw = state.get("player")
    player_dict = player_raw.model_dump() if hasattr(player_raw, "model_dump") else dict(player_raw) if player_raw else None

    if combat_raw:
        combat_dict = combat_raw.model_dump() if hasattr(combat_raw, "model_dump") else dict(combat_raw)
        rounds = combat_dict.get("round", 0)
        participants = combat_dict.get("participants", {})

        alive_names: list[str] = []
        fallen_names: list[str] = []

        scene_units: dict = state.get("scene_units") or {}
        scene_raw = {k: v.model_dump() if hasattr(v, "model_dump") else dict(v) for k, v in scene_units.items()} if hasattr(scene_units, "items") else {}
        dead_units: dict = state.get("dead_units") or {}
        dead_raw = {k: v.model_dump() if hasattr(v, "model_dump") else dict(v) for k, v in dead_units.items()} if hasattr(dead_units, "items") else {}

        # 处理玩家 — HP 已在 player_dict 上保持最新，只需清除战斗覆盖字段
        if player_dict:
            if player_dict.get("hp", 0) > 0:
                alive_names.append(player_dict.get("name", "player"))
            else:
                fallen_names.append(player_dict.get("name", "player"))
            clear_player_combat_fields(player_dict)

        # 处理非玩家单位；友方不会因倒地被清理，便于后续治疗或复活。
        for uid, p in participants.items():
            name = p.get("name", uid)
            if p.get("side") == "ally":
                alive_names.append(name)
                scene_raw[uid] = p
            elif p.get("hp", 0) > 0:
                alive_names.append(name)
                scene_raw[uid] = p
            else:
                fallen_names.append(name)
                dead_raw[uid] = p
                scene_raw.pop(uid, None)

        parts = [f"共进行了 {rounds} 回合。"]
        if alive_names:
            parts.append(f"存活: {', '.join(alive_names)}")
        if fallen_names:
            parts.append(f"倒下: {', '.join(fallen_names)}")
        summary = " ".join(parts)

        dead_unit_ids = list(dead_raw.keys())
        if dead_unit_ids:
            space_raw = state.get("space")
            cleaned_space = _remove_space_units(space_raw, dead_unit_ids)
            if cleaned_space is not None:
                update["space"] = cleaned_space

        update["scene_units"] = scene_raw
        update["dead_units"] = dead_raw

    if player_dict:
        update["player"] = player_dict

    active_start = state.get("active_combat_message_start") if state else None
    combat_archives = _combat_archives_from_state(state)
    if isinstance(active_start, int):
        archive_summary = _build_detailed_combat_archive_summary(summary, state, active_start)
        combat_archives.append(_build_combat_archive(archive_summary, active_start, _message_count(state)))
        update["combat_archives"] = combat_archives

    update["messages"] = [ToolMessage(content=summary, tool_call_id=tool_call_id)]
    return Command(update=update)


@tool
def clear_dead_units(
    unit_ids: list[str] | None = None,
    *,
    state: Annotated[dict, InjectedState] = None,
    tool_call_id: Annotated[str, InjectedToolCallId] = None,
) -> Command:
    """清除死亡单位档案。可指定 ID 列表部分清除，或不传参数清除全部。
    适用于剧情上玩家已完成搜刮尸体、处理遗骸等环节后的清理。
    参数示例：{"unit_ids": ["goblin_1"]}；清除全部用 {}。

    Args:
        unit_ids: 要清除的死亡单位 ID 列表；为空或不传则清除全部。
    """
    return _clear_dead_units_impl(unit_ids, state, tool_call_id)

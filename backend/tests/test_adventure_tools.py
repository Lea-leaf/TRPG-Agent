"""冒险节点工具测试 — 锁定 PDF 节点式推进的最小闭环。"""

from pathlib import Path
import json
import sys

from langgraph.types import Command

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.services.tools.adventure_tools import (  # noqa: E402
    advance_adventure,
    claim_adventure_reward,
    inspect_adventure_state,
    load_adventure_node,
    manage_adventure,
    mark_adventure_event,
    reveal_adventure_clue,
    search_adventure_nodes,
    switch_adventure_node,
)


def _invoke_tool(tool_func, *, tool_input: dict) -> object:
    """用 ToolCall 格式调用 LangChain 工具，保持和现有测试一致。"""
    return tool_func.invoke({
        "name": tool_func.name,
        "args": tool_input,
        "id": "adventure-test-call",
        "type": "tool_call",
    })


def _payload(result: Command) -> dict:
    return json.loads(result.update["messages"][0].content)


def test_load_default_adventure_hook_node():
    result = _invoke_tool(load_adventure_node, tool_input={"state": {}})

    assert isinstance(result, Command)
    payload = _payload(result)
    assert payload["node"]["id"] == "adventure_hook_meet_me_in_phandalin"
    assert payload["node"]["source_pages"] == [4, 5]
    assert payload["progression_rule"].startswith("剧情推进出口只看顶层 available_exits")
    assert payload["available_exits"][0]["id"] == "take_the_road_to_phandalin"
    assert "candidate_exits" not in payload["node"]


def test_manage_adventure_loads_default_node():
    result = _invoke_tool(manage_adventure, tool_input={"action": "load_node", "state": {}})

    assert isinstance(result, Command)
    payload = _payload(result)
    assert payload["node"]["id"] == "adventure_hook_meet_me_in_phandalin"
    assert payload["available_exits"][0]["id"] == "take_the_road_to_phandalin"


def test_inspect_adventure_state_can_load_skill_instructions():
    result = _invoke_tool(
        inspect_adventure_state,
        tool_input={"include_help": True, "state": {}},
    )

    content = result.update["messages"][0].content
    assert "冒险模组主持技能" in content
    assert "manage_adventure" in content
    assert 'action="load_node"' in content


def test_manage_adventure_help_loads_skill_instructions():
    result = _invoke_tool(manage_adventure, tool_input={"action": "help", "state": {}})

    content = result.update["messages"][0].content
    assert "冒险模组主持技能" in content
    assert "manage_adventure" in content
    assert 'action="search_nodes"' in content
    assert 'action="resolve"' in content
    assert 'action="reveal_clue"' not in content
    assert 'action="mark_event"' not in content


def test_manage_adventure_schema_exposes_only_hosting_path_actions():
    schema = manage_adventure.args_schema.model_json_schema()
    assert schema["properties"]["action"]["enum"] == [
        "help",
        "load_node",
        "search_nodes",
        "switch_node",
        "resolve",
        "advance",
    ]
    assert "clue_id" not in schema["properties"]
    assert "event_id" not in schema["properties"]
    assert "include_help" not in schema["properties"]


def test_manage_adventure_advance_settles_single_exit_local_requirements():
    state = {
        "adventure": {
            "module_id": "lost_mine",
            "active_node_id": "adventure_hook_meet_me_in_phandalin",
            "unlocked_node_ids": ["adventure_hook_meet_me_in_phandalin"],
            "completed_node_ids": [],
            "known_clue_ids": [],
            "completed_event_ids": [],
            "claimed_reward_ids": [],
            "pending_exit_option_ids": [],
        }
    }

    advanced = _invoke_tool(
        manage_adventure,
        tool_input={
            "action": "advance",
            "option_id": "take_the_road_to_phandalin",
            "state": state,
        },
    )

    adventure = advanced.update["adventure"]
    assert adventure["active_node_id"] == "goblin_ambush"
    assert adventure["completed_node_ids"] == ["adventure_hook_meet_me_in_phandalin"]
    assert "depart_neverwinter_for_phandalin" in adventure["completed_event_ids"]
    assert {"delivery_job", "phandalin_destination"}.issubset(set(adventure["known_clue_ids"]))


def test_advance_requires_completed_event_when_exit_has_condition():
    state = {
        "adventure": {
            "module_id": "lost_mine",
            "active_node_id": "goblin_ambush",
            "unlocked_node_ids": ["goblin_ambush"],
            "completed_node_ids": [],
            "known_clue_ids": [],
            "completed_event_ids": [],
            "pending_exit_option_ids": [],
        }
    }

    blocked = _invoke_tool(
        advance_adventure,
        tool_input={"option_id": "follow_goblin_trail", "state": state},
    )
    assert "出口条件未满足" in _payload(blocked)["error"]

    marked = _invoke_tool(
        mark_adventure_event,
        tool_input={"event_id": "goblin_ambush_resolved", "state": state},
    )
    state["adventure"] = marked.update["adventure"]

    still_blocked = _invoke_tool(
        advance_adventure,
        tool_input={"option_id": "follow_goblin_trail", "state": state},
    )
    assert "出口条件未满足" in _payload(still_blocked)["error"]

    revealed = _invoke_tool(
        reveal_adventure_clue,
        tool_input={"clue_id": "goblin_trail", "state": state},
    )
    state["adventure"] = revealed.update["adventure"]

    advanced = _invoke_tool(
        advance_adventure,
        tool_input={"option_id": "follow_goblin_trail", "state": state},
    )
    assert advanced.update["adventure"]["active_node_id"] == "goblin_trail_to_cragmaw_hideout"
    assert "goblin_ambush" in advanced.update["adventure"]["completed_node_ids"]
    assert advanced.update["adventure"]["breadcrumb_node_ids"][-1] == "goblin_trail_to_cragmaw_hideout"
    assert advanced.update["adventure"]["deferred_node_ids"] == []


def test_manage_adventure_can_resolve_clue_and_advance():
    state = {
        "player": {"name": "英雄", "xp": 0},
        "adventure": {
            "module_id": "lost_mine",
            "active_node_id": "goblin_ambush",
            "unlocked_node_ids": ["goblin_ambush"],
            "completed_node_ids": [],
            "known_clue_ids": [],
            "completed_event_ids": [],
            "pending_exit_option_ids": [],
        }
    }

    resolved = _invoke_tool(
        manage_adventure,
        tool_input={"action": "resolve", "clue_ids": ["goblin_trail"], "event_ids": ["goblin_ambush_resolved"], "state": state},
    )
    state["adventure"] = resolved.update["adventure"]

    advanced = _invoke_tool(
        manage_adventure,
        tool_input={"action": "advance", "option_id": "follow_goblin_trail", "state": state},
    )

    assert advanced.update["adventure"]["active_node_id"] == "goblin_trail_to_cragmaw_hideout"

    state["adventure"] = advanced.update["adventure"]

    trail_resolved = _invoke_tool(
        manage_adventure,
        tool_input={"action": "resolve", "event_ids": ["reach_cragmaw_hideout_trail_end"], "state": state},
    )
    state["adventure"] = trail_resolved.update["adventure"]

    hideout = _invoke_tool(
        manage_adventure,
        tool_input={"action": "advance", "option_id": "arrive_cragmaw_hideout", "state": state},
    )

    assert hideout.update["adventure"]["active_node_id"] == "cragmaw_hideout_entrance"
    assert hideout.update["adventure"]["claimed_reward_ids"] == []
    assert hideout.update["adventure"]["pending_reward_grants"][0]["id"] == "goblin_ambush_hideout_75_xp"
    assert "reach_cragmaw_hideout" in hideout.update["adventure"]["completed_event_ids"]
    assert "player" not in hideout.update

    claimed = _invoke_tool(
        claim_adventure_reward,
        tool_input={
            "reward_id": "goblin_ambush_hideout_75_xp",
            "state": {"player": state["player"], "adventure": hideout.update["adventure"]},
        },
    )
    assert claimed.update["player"]["xp"] == 75
    assert claimed.update["adventure"]["claimed_reward_ids"] == ["goblin_ambush_hideout_75_xp"]
    assert claimed.update["adventure"]["pending_reward_grants"] == []
    claim_payload = _payload(claimed)
    assert "adventure_state" not in claim_payload
    assert "reward" not in claim_payload["result"]
    assert claim_payload["result"]["reward_id"] == "goblin_ambush_hideout_75_xp"
    assert claim_payload["result"]["amount"] == 75
    assert claim_payload["result"]["current_xp"] == 75
    assert "打败伏击地精" in claim_payload["result"]["description"]
    assert "打败伏击地精" in claim_payload["message"]

    repeated = _invoke_tool(
        claim_adventure_reward,
        tool_input={
            "reward_id": "goblin_ambush_hideout_75_xp",
            "state": {"player": claimed.update["player"], "adventure": claimed.update["adventure"]},
        },
    )
    assert "player" not in repeated.update
    assert "待领取奖励不存在" in _payload(repeated)["result"]["error"]
    assert "adventure_state" not in _payload(repeated)


def test_manage_adventure_resolve_returns_available_exits_after_scene_result():
    state = {
        "adventure": {
            "module_id": "lost_mine",
            "active_node_id": "goblin_ambush",
            "unlocked_node_ids": ["goblin_ambush"],
            "completed_node_ids": [],
            "known_clue_ids": [],
            "completed_event_ids": [],
            "pending_exit_option_ids": [],
        }
    }

    resolved = _invoke_tool(
        manage_adventure,
        tool_input={
            "action": "resolve",
            "outcome": "地精伏击已结束，玩家发现了通向窝点的踪迹。",
            "clue_ids": ["goblin_trail"],
            "event_ids": ["goblin_ambush_resolved"],
            "state": state,
        },
    )

    payload = _payload(resolved)
    assert "goblin_trail" in resolved.update["adventure"]["known_clue_ids"]
    assert "goblin_ambush_resolved" in resolved.update["adventure"]["completed_event_ids"]
    assert payload["recommended_action"]["tool"] == "ask_player_or_advance_declared_choice"
    assert payload["recommended_action"]["available_option_ids"] == [
        "follow_goblin_trail",
        "continue_to_phandalin",
    ]


def test_manage_adventure_resolve_rejects_events_outside_current_node():
    state = {
        "adventure": {
            "module_id": "lost_mine",
            "active_node_id": "lost_mine_start",
            "unlocked_node_ids": ["lost_mine_start"],
            "completed_node_ids": [],
            "known_clue_ids": [],
            "completed_event_ids": [],
            "pending_exit_option_ids": [],
        }
    }

    resolved = _invoke_tool(
        manage_adventure,
        tool_input={"action": "resolve", "event_ids": ["goblin_ambush_resolved"], "state": state},
    )

    assert resolved.update["adventure"]["completed_event_ids"] == []


def test_compat_mark_event_rejects_events_outside_current_node():
    result = _invoke_tool(
        mark_adventure_event,
        tool_input={
            "event_id": "goblin_ambush_resolved",
            "state": {
                "adventure": {
                    "module_id": "lost_mine",
                    "active_node_id": "lost_mine_start",
                    "unlocked_node_ids": ["lost_mine_start"],
                    "completed_node_ids": [],
                    "known_clue_ids": [],
                    "completed_event_ids": [],
                    "pending_exit_option_ids": [],
                }
            },
        },
    )

    payload = _payload(result)
    assert "事件不属于当前节点" in payload["error"]
    assert "adventure" not in result.update


def test_advance_with_event_id_returns_exit_hint():
    result = _invoke_tool(
        manage_adventure,
        tool_input={"action": "advance", "option_id": "goblin_ambush_resolved", "state": {}},
    )

    payload = _payload(result)
    assert "当前节点没有出口" in payload["error"]
    assert "available_exits.id" in payload["hint"]
    assert payload["available_exit_ids"] == ["take_the_road_to_phandalin"]


def test_search_adventure_nodes_finds_module_material():
    result = _invoke_tool(
        search_adventure_nodes,
        tool_input={"query": "地精伏击", "state": {}},
    )

    payload = _payload(result)
    result_ids = [item["id"] for item in payload["results"]]
    assert "goblin_ambush" in result_ids


def test_load_ambush_node_includes_pdf_guidance():
    result = _invoke_tool(
        load_adventure_node,
        tool_input={"node_id": "goblin_ambush", "state": {}},
    )

    payload = _payload(result)
    node = payload["node"]
    assert node["scene_beats"]
    assert any("伏击" in beat for beat in node["scene_beats"])
    assert any("新版突袭规则" in note for note in node["rules_notes"])
    assert any(clue["id"] == "goblin_trail" for clue in node["clues"])
    assert node["fallbacks"]


def test_load_ambush_node_overrides_legacy_surprise_rule():
    result = _invoke_tool(
        load_adventure_node,
        tool_input={"node_id": "goblin_ambush", "state": {}},
    )

    payload = _payload(result)
    node = payload["node"]
    visible_text = json.dumps(node, ensure_ascii=False)
    assert "第一轮无法执行任何动作" not in visible_text
    assert "新版突袭规则" in visible_text
    assert "先攻检定上获得劣势" in visible_text
    assert "不跳过首回合" in visible_text


def test_search_adventure_nodes_uses_dm_guidance_and_subsections():
    rest_result = _invoke_tool(
        search_adventure_nodes,
        tool_input={"query": "休息 75 XP", "state": {}},
    )
    reward_result = _invoke_tool(
        search_adventure_nodes,
        tool_input={"query": "75 XP 奖励经验值", "state": {}},
    )

    rest_ids = [item["id"] for item in _payload(rest_result)["results"]]
    reward_ids = [item["id"] for item in _payload(reward_result)["results"]]
    assert "cragmaw_hideout_entrance" in rest_ids
    assert "cragmaw_hideout_entrance" in reward_ids
    assert any(item in rest_ids for item in ["cragmaw_hideout_klarg_cave", "cragmaw_hideout_treasure_and_milestone"])


def test_switch_adventure_node_updates_bookmark_without_exit_requirement():
    state = {
        "adventure": {
            "module_id": "lost_mine",
            "active_node_id": "lost_mine_start",
            "unlocked_node_ids": ["lost_mine_start"],
            "completed_node_ids": [],
            "known_clue_ids": [],
            "completed_event_ids": [],
            "pending_exit_option_ids": [],
        }
    }

    result = _invoke_tool(
        switch_adventure_node,
        tool_input={
            "node_id": "phandalin_arrival",
            "reason": "玩家决定暂时不追踪地精，继续护送补给。",
            "state": state,
        },
    )

    assert result.update["adventure"]["active_node_id"] == "phandalin"
    assert result.update["adventure"]["completed_node_ids"] == []
    assert result.update["adventure"]["deferred_node_ids"] == ["lost_mine_start"]
    assert result.update["adventure"]["breadcrumb_node_ids"] == ["lost_mine_start", "phandalin"]
    payload = _payload(result)
    assert payload["result"]["to"] == "phandalin"

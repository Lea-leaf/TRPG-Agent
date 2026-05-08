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
    inspect_adventure_state,
    load_adventure_node,
    manage_adventure,
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


def test_load_default_lost_mine_start_node():
    result = _invoke_tool(load_adventure_node, tool_input={"state": {}})

    assert isinstance(result, Command)
    payload = _payload(result)
    assert payload["node"]["id"] == "lost_mine_start"
    assert payload["node"]["source_pages"] == [6, 6]
    assert payload["available_exits"][0]["id"] == "continue_to_ambush"


def test_manage_adventure_loads_default_node():
    result = _invoke_tool(manage_adventure, tool_input={"action": "load_node", "state": {}})

    assert isinstance(result, Command)
    payload = _payload(result)
    assert payload["node"]["id"] == "lost_mine_start"
    assert payload["available_exits"][0]["id"] == "continue_to_ambush"


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


def test_advance_requires_revealed_clue_when_exit_has_condition():
    state = {
        "adventure": {
            "module_id": "lost_mine",
            "active_node_id": "goblin_ambush",
            "unlocked_node_ids": ["lost_mine_start", "goblin_ambush"],
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

    revealed = _invoke_tool(
        reveal_adventure_clue,
        tool_input={"clue_id": "goblin_trail", "state": state},
    )
    state["adventure"] = revealed.update["adventure"]

    advanced = _invoke_tool(
        advance_adventure,
        tool_input={"option_id": "follow_goblin_trail", "state": state},
    )
    assert advanced.update["adventure"]["active_node_id"] == "cragmaw_hideout_entrance"
    assert "goblin_ambush" in advanced.update["adventure"]["completed_node_ids"]


def test_manage_adventure_can_reveal_clue_and_advance():
    state = {
        "adventure": {
            "module_id": "lost_mine",
            "active_node_id": "goblin_ambush",
            "unlocked_node_ids": ["lost_mine_start", "goblin_ambush"],
            "completed_node_ids": [],
            "known_clue_ids": [],
            "completed_event_ids": [],
            "pending_exit_option_ids": [],
        }
    }

    revealed = _invoke_tool(
        manage_adventure,
        tool_input={"action": "reveal_clue", "clue_id": "goblin_trail", "state": state},
    )
    state["adventure"] = revealed.update["adventure"]

    advanced = _invoke_tool(
        manage_adventure,
        tool_input={"action": "advance", "option_id": "follow_goblin_trail", "state": state},
    )

    assert advanced.update["adventure"]["active_node_id"] == "cragmaw_hideout_entrance"


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
    assert "轮到地精行动时" in node["source_text"]
    assert "75 XP" in node["source_text"]
    assert node["dm_guidance"]["tactics"]
    assert node["dm_guidance"]["xp"]


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
    assert "goblin_ambush__休息" in rest_ids
    assert "goblin_ambush__奖励经验值" in reward_ids


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

    assert result.update["adventure"]["active_node_id"] == "phandalin_arrival"
    assert "lost_mine_start" in result.update["adventure"]["completed_node_ids"]
    payload = _payload(result)
    assert payload["result"]["to"] == "phandalin_arrival"

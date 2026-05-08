import json
import unittest

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.graph.constants import COMBAT_AGENT_MODE, NARRATIVE_AGENT_MODE
from app.memory.context_assembler import ContextAssembler, summarize_tool_message


class _StaticContextProvider:
    def get_context_blocks(self, *, state, mode):
        return [f"外部上下文:{mode}"]


class ContextAssemblerTests(unittest.TestCase):
    def test_assemble_includes_summary_external_context_and_hud(self):
        assembler = ContextAssembler(external_context_provider=_StaticContextProvider())
        state = {
            "conversation_summary": "玩家刚踏入地牢入口。",
            "messages": [HumanMessage(content="我看看四周。")],
            "player": {"id": "player_hero", "name": "英雄", "role_class": "法师"},
            "scene_units": {"goblin_1": {"name": "Goblin", "side": "enemy", "hp": 7, "max_hp": 7}},
        }

        assembled = assembler.assemble(state, NARRATIVE_AGENT_MODE, base_system_prompt="基础规则")

        self.assertEqual("基础规则", assembled.system_prompt)
        self.assertNotIn("[可按需加载的技能]", assembled.system_prompt)
        self.assertNotIn("character_state_management", assembled.system_prompt)
        self.assertIn("玩家刚踏入地牢入口。", assembled.runtime_state_text)
        self.assertIn("[扩展上下文]", assembled.runtime_state_text)
        self.assertIn("外部上下文:narrative", assembled.runtime_state_text)
        self.assertIn("状态快照", assembled.hud_text)
        self.assertEqual("我看看四周。", assembled.model_input_messages[-2].content)
        self.assertIsInstance(assembled.model_input_messages[-1], SystemMessage)
        self.assertIn("<runtime_state", assembled.model_input_messages[-1].content)
        self.assertIn('source="hud"', assembled.model_input_messages[-1].content)
        self.assertIn('visibility="model_only"', assembled.model_input_messages[-1].content)
        self.assertNotIn("复述", assembled.model_input_messages[-1].content)
        self.assertNotIn("解释", assembled.model_input_messages[-1].content)
        self.assertIn("状态快照", assembled.model_input_messages[-1].content)
        self.assertIn("[当前平面空间]", assembled.hud_text)
        self.assertIn("当前没有平面地图", assembled.hud_text)

    def test_episodic_context_precedes_summary_fallback(self):
        assembler = ContextAssembler()
        state = {
            "conversation_summary": "这是旧摘要，不应在有 episodic context 时继续注入。",
            "episodic_context": ["玩家刚进入地牢。", "上一轮已经听见祭坛后的脚步声。"],
            "messages": [HumanMessage(content="我推开门。")],
        }

        assembled = assembler.assemble(state, NARRATIVE_AGENT_MODE, base_system_prompt="基础规则")

        self.assertIn("[近期情节记忆]", assembled.runtime_state_text)
        self.assertIn("玩家刚进入地牢。", assembled.runtime_state_text)
        self.assertNotIn("这是旧摘要", assembled.runtime_state_text)

    def test_opening_prompt_requests_fighter_companion_when_missing(self):
        assembler = ContextAssembler()
        state = {
            "messages": [HumanMessage(content="开始冒险。")],
            "player": {"id": "player_hero", "name": "英雄", "side": "player"},
        }

        assembled = assembler.assemble(state, NARRATIVE_AGENT_MODE, base_system_prompt="基础规则")

        self.assertIn("[开局友方准则]", assembled.runtime_state_text)
        self.assertIn("fighter_companion", assembled.runtime_state_text)

    def test_opening_prompt_skips_when_ally_exists(self):
        assembler = ContextAssembler()
        state = {
            "messages": [HumanMessage(content="开始冒险。")],
            "player": {"id": "player_hero", "name": "英雄", "side": "player"},
            "scene_units": {"fighter_companion": {"id": "fighter_companion", "name": "米拉", "side": "ally"}},
        }

        assembled = assembler.assemble(state, NARRATIVE_AGENT_MODE, base_system_prompt="基础规则")

        self.assertNotIn("[开局友方准则]", assembled.runtime_state_text)

    def test_hud_marks_ally_scene_unit_id_as_start_combat_input(self):
        assembler = ContextAssembler()
        state = {
            "messages": [HumanMessage(content="开战。")],
            "scene_units": {
                "fighter_companion": {
                    "id": "fighter_companion",
                    "name": "米拉",
                    "side": "ally",
                    "hp": 12,
                    "max_hp": 12,
                },
                "goblin_1": {"id": "goblin_1", "name": "Goblin", "side": "enemy", "hp": 7, "max_hp": 7},
            },
        }

        assembled = assembler.assemble(state, NARRATIVE_AGENT_MODE, base_system_prompt="基础规则")

        self.assertIn("start_combat 的非玩家参战 ID 来源", assembled.hud_text)
        self.assertIn("敌人和友方都必须显式列入 combatant_ids", assembled.hud_text)
        self.assertIn('start_combat.combatant_ids 可直接使用 "fighter_companion"', assembled.hud_text)
        self.assertIn('start_combat.combatant_ids 可直接使用 "goblin_1"', assembled.hud_text)

    def test_narrative_runtime_state_periodically_anchors_adventure_node(self):
        assembler = ContextAssembler()
        state = {
            "messages": [HumanMessage(content=f"探索 {index}") for index in range(4)],
            "adventure": {"module_id": "lost_mine", "active_node_id": "goblin_ambush"},
        }

        assembled = assembler.assemble(state, NARRATIVE_AGENT_MODE, base_system_prompt="基础规则")

        self.assertIn("[冒险节点校准]", assembled.runtime_state_text)
        self.assertIn("goblin_ambush", assembled.runtime_state_text)
        self.assertIn("不要因为多轮闲聊而脱离当前模组进度", assembled.runtime_state_text)

    def test_adventure_node_anchor_skips_combat_mode(self):
        assembler = ContextAssembler()
        state = {
            "messages": [HumanMessage(content=f"继续 {index}") for index in range(4)],
            "adventure": {"module_id": "lost_mine", "active_node_id": "goblin_ambush"},
            "combat": {
                "round": 1,
                "current_actor_id": "goblin_1",
                "initiative_order": ["goblin_1"],
                "participants": {
                    "goblin_1": {"name": "Goblin", "side": "enemy", "hp": 7, "max_hp": 7, "ac": 15}
                },
            },
        }

        assembled = assembler.assemble(state, COMBAT_AGENT_MODE, base_system_prompt="战斗规则")

        self.assertNotIn("[冒险节点校准]", assembled.runtime_state_text)

    def test_assemble_trims_without_starting_from_tool_message(self):
        assembler = ContextAssembler()
        messages = [HumanMessage(content="旧消息")]
        messages.append(AIMessage(content="", tool_calls=[{"name": "attack_action", "args": {}, "id": "call_1"}]))
        messages.append(ToolMessage(content="Goblin 使用弯刀攻击。\n英雄 HP: 18 -> 13", tool_call_id="call_1", name="attack_action"))
        messages.extend(HumanMessage(content=f"消息 {index}") for index in range(39))

        assembled = assembler.assemble({"messages": messages}, NARRATIVE_AGENT_MODE, base_system_prompt="基础规则")

        self.assertIsInstance(assembled.model_input_messages[0], AIMessage)
        tool_messages = [message for message in assembled.model_input_messages if isinstance(message, ToolMessage)]
        self.assertEqual(1, len(tool_messages))
        self.assertIn("[工具:attack_action]", tool_messages[0].content)

    def test_hud_preserves_trailing_tool_exchange_for_followup_call(self):
        assembler = ContextAssembler()
        state = {
            "messages": [
                HumanMessage(content="continue"),
                AIMessage(
                    content="",
                    tool_calls=[{"name": "attack_action", "args": {"attacker_id": "goblin_1"}, "id": "call_1"}],
                ),
                ToolMessage(content="attack resolved", tool_call_id="call_1", name="attack_action"),
            ]
        }

        assembled = assembler.assemble(state, COMBAT_AGENT_MODE, base_system_prompt="combat rules")

        self.assertIsInstance(assembled.model_input_messages[-3], SystemMessage)
        self.assertIsInstance(assembled.model_input_messages[-2], AIMessage)
        self.assertIsInstance(assembled.model_input_messages[-1], ToolMessage)
        self.assertIn("<runtime_state", assembled.model_input_messages[-3].content)
        self.assertIn("[工具:attack_action]", assembled.model_input_messages[-1].content)

    def test_adventure_node_tool_projection_keeps_structured_material(self):
        tool_message = ToolMessage(
            content=json.dumps(
                {
                    "node": {
                        "id": "goblin_ambush",
                        "title": "地精伏击",
                        "kind": "encounter",
                        "source_pages": [6, 7],
                        "source_excerpt": "伏击摘录",
                        "source_text": "轮到地精行动时，其中两个地精冲出灌木丛。打败伏击的地精并发现克拉摩窝点后，每人75 XP。",
                        "subsections": [{"title": "奖励经验值", "text": "每人75 XP"}],
                        "dm_summary": "四只地精伏击。",
                        "player_visible_intro": "两匹死马挡在路上。",
                        "secrets": ["地精躲在灌木丛"],
                        "checks": [{"ability": "wis", "skill": "survival", "dc": 10}],
                        "encounters": [{"monster_slug": "goblin", "count": 4}],
                        "rewards": [{"type": "xp", "description": "75 XP"}],
                        "clues": [{"id": "goblin_trail", "label": "地精踪迹"}],
                        "events": [],
                        "dm_guidance": {"tactics": ["两近战两远程"], "xp": ["75 XP"]},
                        "rules_overrides": [{"topic": "surprise", "rule": "新版突袭只让先攻劣势"}],
                        "candidate_exits": [{"id": "goblin_trail"}],
                    },
                    "available_exits": [{"id": "follow_goblin_trail", "available": False}],
                    "adventure_state": {"known_clue_ids": []},
                },
                ensure_ascii=False,
            ),
            tool_call_id="call_adventure",
            name="load_adventure_node",
        )

        projected = summarize_tool_message(tool_message)

        self.assertIn("轮到地精行动时", projected)
        self.assertIn("goblin_trail", projected)
        self.assertIn("新版突袭只让先攻劣势", projected)
        self.assertIn("available_exits", projected)

    def test_archived_combat_expands_start_to_triggering_ai_tool_call(self):
        assembler = ContextAssembler()
        state = {
            "messages": [
                HumanMessage(content="狼冲出来了。"),
                AIMessage(content="", tool_calls=[{"name": "start_combat", "args": {"combatant_ids": ["wolf_1"]}, "id": "call_start"}]),
                ToolMessage(content="战斗开始！第 1 回合。", tool_call_id="call_start", name="start_combat"),
                AIMessage(content="", tool_calls=[{"name": "end_combat", "args": {}, "id": "call_end"}]),
                ToolMessage(content="共进行了 1 回合。 倒下: Wolf", tool_call_id="call_end", name="end_combat"),
                HumanMessage(content="我检查四周。"),
            ],
            "combat_archives": [
                {
                    "summary": "法师击倒了野狼，战斗结束。",
                    "start_index": 2,
                    "end_index": 4,
                }
            ],
        }

        assembled = assembler.assemble(state, NARRATIVE_AGENT_MODE, base_system_prompt="基础规则")

        dangling_tool_call_messages = [
            message for message in assembled.model_input_messages
            if isinstance(message, AIMessage) and message.tool_calls
        ]
        self.assertEqual([], dangling_tool_call_messages)
        self.assertTrue(any(
            isinstance(message, HumanMessage)
            and isinstance(message.content, str)
            and message.content.startswith("[系统:战斗归档]")
            for message in assembled.model_input_messages
        ))

    def test_projection_strips_legacy_dangling_tool_call(self):
        assembler = ContextAssembler()
        state = {
            "messages": [
                HumanMessage(content="结束战斗。"),
                AIMessage(content="战斗结束。", tool_calls=[{"name": "end_combat", "args": {}, "id": "call_end"}]),
                AIMessage(content="你确认周围暂时安全。", tool_calls=[]),
            ],
        }

        assembled = assembler.assemble(state, NARRATIVE_AGENT_MODE, base_system_prompt="基础规则")

        ai_messages = [message for message in assembled.model_input_messages if isinstance(message, AIMessage)]
        self.assertTrue(any(message.content == "战斗结束。" for message in ai_messages))
        self.assertFalse(any(message.tool_calls for message in ai_messages))

    def test_assemble_adds_combat_brief_and_turn_directive(self):
        assembler = ContextAssembler()
        state = {
            "messages": [HumanMessage(content="我攻击哥布林")],
            "player": {"id": "player_hero", "name": "英雄", "side": "player", "hp": 12, "max_hp": 12, "ac": 14, "attacks": [{"name": "法杖"}]},
            "combat": {
                "round": 2,
                "current_actor_id": "goblin_1",
                "initiative_order": ["goblin_1", "player_hero"],
                "participants": {
                    "goblin_1": {"name": "Goblin", "side": "enemy", "hp": 7, "max_hp": 7, "ac": 15, "attacks": [{"name": "Scimitar"}]}
                },
            },
        }

        assembled = assembler.assemble(state, COMBAT_AGENT_MODE, base_system_prompt="战斗规则")

        self.assertEqual("战斗规则", assembled.system_prompt)
        self.assertIn("[战斗简报]", assembled.runtime_state_text)
        self.assertIn("[当前回合指令]", assembled.runtime_state_text)
        self.assertIn("Goblin", assembled.runtime_state_text)

    def test_combat_context_lists_monster_actions(self):
        assembler = ContextAssembler()
        state = {
            "messages": [HumanMessage(content="继续战斗。")],
            "combat": {
                "round": 1,
                "current_actor_id": "goblin_1",
                "initiative_order": ["goblin_1"],
                "participants": {
                    "goblin_1": {
                        "name": "Goblin",
                        "side": "enemy",
                        "hp": 7,
                        "max_hp": 7,
                        "ac": 15,
                        "actions": [
                            {"id": "scimitar", "name": "Scimitar", "kind": "attack"},
                            {"id": "nimble_escape", "name": "Nimble Escape", "kind": "bonus_action"},
                        ],
                        "attacks": [{"name": "Scimitar"}],
                    }
                },
            },
        }

        assembled = assembler.assemble(state, COMBAT_AGENT_MODE, base_system_prompt="战斗规则")

        self.assertIn("actions:Scimitar(scimitar, attack)", assembled.runtime_state_text)
        self.assertIn("actions=[Scimitar(scimitar, attack)", assembled.hud_text)
        self.assertNotIn("attacks:[", assembled.runtime_state_text)

    def test_combat_context_separates_allies_and_projects_resources(self):
        assembler = ContextAssembler()
        state = {
            "messages": [HumanMessage(content="继续战斗。")],
            "player": {"id": "player_hero", "name": "英雄", "side": "player", "hp": 10, "max_hp": 12, "ac": 16},
            "combat": {
                "round": 1,
                "current_actor_id": "apprentice_wizard",
                "initiative_order": ["apprentice_wizard", "goblin_1", "player_hero"],
                "participants": {
                    "apprentice_wizard": {
                        "id": "apprentice_wizard",
                        "name": "伊莲",
                        "side": "ally",
                        "hp": 12,
                        "max_hp": 12,
                        "ac": 12,
                        "resources": {"spell_slot_lv1": 2},
                        "resource_caps": {"spell_slot_lv1": 3},
                        "known_spells": ["magic_missile", "shield"],
                        "known_cantrips": ["fire_bolt"],
                        "reaction_available": True,
                        "attacks": [{"name": "Dagger"}],
                        "behavior_profile": "保持距离并保护玩家。",
                    },
                    "goblin_1": {"name": "Goblin", "side": "enemy", "hp": 7, "max_hp": 7, "ac": 15},
                },
            },
        }

        assembled = assembler.assemble(state, COMBAT_AGENT_MODE, base_system_prompt="战斗规则")

        self.assertIn("友方侧: 伊莲", assembled.runtime_state_text)
        self.assertIn("对立侧: Goblin", assembled.runtime_state_text)
        self.assertIn("spell_slot_lv1=2/3", assembled.runtime_state_text)
        self.assertIn("magic_missile", assembled.hud_text)
        self.assertIn("reaction=可用: shield", assembled.hud_text)
        self.assertIn("当前是友方单位 伊莲", assembled.runtime_state_text)
        self.assertIn("以该友方单位 ID 作为行动者/施法者", assembled.runtime_state_text)

    def test_hud_includes_planar_space_summary(self):
        assembler = ContextAssembler()
        state = {
            "messages": [HumanMessage(content="我观察站位。")],
            "space": {
                "active_map_id": "map_hall",
                "maps": {
                    "map_hall": {
                        "id": "map_hall",
                        "name": "大厅",
                        "width": 80,
                        "height": 60,
                        "grid_size": 5,
                    }
                },
                "placements": {
                    "goblin_1": {
                        "unit_id": "goblin_1",
                        "map_id": "map_hall",
                        "position": {"x": 10, "y": 15},
                        "facing_deg": 90,
                    }
                },
            },
        }

        assembled = assembler.assemble(state, NARRATIVE_AGENT_MODE, base_system_prompt="基础规则")

        self.assertIn("[当前平面空间]", assembled.hud_text)
        self.assertIn("大厅", assembled.hud_text)
        self.assertIn("当前地图单位坐标", assembled.hud_text)
        self.assertIn("goblin_1: (10, 15)", assembled.hud_text)

    def test_inspect_unit_tool_projection_keeps_structured_character_facts(self):
        tool_message = ToolMessage(
            content=(
                "[玩家角色] player_hero 完整信息:\n"
                '{"id":"player_hero","name":"英雄","role_class":"法师","level":2,'
                '"hp":8,"max_hp":12,"resources":{"spell_slot_lv1":1},'
                '"conditions":[{"id":"arcane_ward","extra":{"ward_hp":7}}],'
                '"known_spells":["magic_missile","shield"],'
                '"long_notes":"这段冗长说明不应挤掉关键结构字段"}'
            ),
            tool_call_id="call_1",
            name="inspect_unit",
        )

        projected = summarize_tool_message(tool_message)

        self.assertIn("[工具:inspect_unit]", projected)
        self.assertIn("spell_slot_lv1", projected)
        self.assertIn("magic_missile", projected)
        self.assertIn("arcane_ward", projected)
        self.assertIn("long_notes", projected)

    def test_cast_spell_projection_keeps_multi_target_hp_results(self):
        tool_message = ToolMessage(
            content=(
                "伊莲 施放 魔法飞弹（1环）— 3 枚飞弹!\n"
                "  → Goblin A: 2枚 [1d4+1 (2), 1d4+1 (3)] = 5 力场伤害\n"
                "  Goblin A HP: 7 → 2\n"
                "  → Goblin B: 1枚 [1d4+1 (4)] = 4 力场伤害\n"
                "  Goblin B HP: 7 → 3\n"
                "（剩余1环法术位: 2）"
            ),
            tool_call_id="call_spell",
            name="cast_spell",
        )

        projected = summarize_tool_message(tool_message)

        self.assertIn("Goblin A HP: 7 → 2", projected)
        self.assertIn("Goblin B HP: 7 → 3", projected)
        self.assertIn("剩余1环法术位", projected)

    def test_attack_projection_keeps_hp_resolution_line(self):
        tool_message = ToolMessage(
            content=(
                "Goblin 2 使用 [Scimitar] 攻击 巴伦!\n"
                "命中骰: 2d20kh1 (10, 14)+ 4 = 18 vs AC 16\n"
                "伤害骰: 1d6 (6)+ 2 = 8 → 8 点 slashing 伤害\n"
                "巴伦 HP: 12 → 4"
            ),
            tool_call_id="call_attack",
            name="use_monster_action",
        )

        projected = summarize_tool_message(tool_message)

        self.assertIn("巴伦 HP: 12 → 4", projected)
        self.assertIn("已经由工具写回", projected)
        self.assertIn("不得再次扣减", projected)

    def test_any_tool_projection_keeps_hp_resolution_line(self):
        tool_message = ToolMessage(
            content=(
                "巴伦饮下治疗药水。\n"
                "治疗骰: 2d4+2 = 7\n"
                "巴伦 HP: 4 → 11"
            ),
            tool_call_id="call_state",
            name="modify_character_state",
        )

        projected = summarize_tool_message(tool_message)

        self.assertIn("巴伦 HP: 4 → 11", projected)
        self.assertIn("不得再次扣减、治疗或改写 HP", projected)


if __name__ == "__main__":
    unittest.main()

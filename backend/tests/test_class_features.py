"""职业特性框架测试。"""

from __future__ import annotations

import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.services.class_features import (
    FeatureContext,
    FeatureResult,
    available_features,
    get_critical_threshold,
    grant_spellcasting,
    register_feature,
    run_feature,
    sync_eldritch_knight_spellcasting,
)
from app.services.tool_service import use_class_feature


def test_get_critical_threshold_respects_champion_only():
    """重击阈值只应被勇士职业特性下调到 19。"""
    assert get_critical_threshold({"class_features": []}) == 20
    assert get_critical_threshold({"class_features": ["improved_critical"]}) == 19
    assert get_critical_threshold({"class_features": ["combat_superiority", "student_of_war"]}) == 20


def test_grant_spellcasting_writes_shared_spell_fields():
    """通用施法 helper 应把法术字段一次性写回角色卡。"""
    player = {"modifiers": {"int": 3}, "resources": {}, "resource_caps": {}}

    grant_spellcasting(
        player,
        ability="int",
        cantrips=["fire_bolt", "ray_of_frost"],
        spells=["shield", "magic_missile", "burning_hands"],
        spell_slots={"spell_slot_lv1": 2},
    )

    assert player["spellcasting_ability"] == "int"
    assert player["resources"]["spell_slot_lv1"] == 2
    assert player["resource_caps"]["spell_slot_lv1"] == 2
    assert player["spell_save_dc"] == 13
    assert player["spell_attack_bonus"] == 5
    assert "fire_bolt" in player["known_cantrips"]
    assert "shield" in player["known_spells"]


def test_sync_eldritch_knight_spellcasting_uses_level_3_to_5_table():
    """奥法骑士施法同步应按 3-5 级职业表刷新法术位和已知法术数量。"""
    player = {
        "level": 4,
        "fighter_archetype": "eldritch_knight",
        "modifiers": {"int": 1},
        "proficiency_bonus": 2,
        "resources": {},
        "resource_caps": {},
    }

    lines = sync_eldritch_knight_spellcasting(player)

    assert player["eldritch_knight_cantrips_known"] == 2
    assert player["eldritch_knight_spells_known"] == 4
    assert player["resources"]["spell_slot_lv1"] == 3
    assert player["resource_caps"]["spell_slot_lv1"] == 3
    assert player["spell_save_dc"] == 11
    assert player["spell_attack_bonus"] == 3
    assert "thunderwave" in player["known_spells"]
    assert "奥法骑士施法表同步" in lines[0]


def test_registry_registers_and_runs_feature_handler():
    """注册表应支持最小的特性分发。"""
    feature_id = "test_feature_dispatch"

    def handler(context: FeatureContext) -> FeatureResult:
        return FeatureResult(lines=["ok"], update={"seen": context.payload})

    register_feature(feature_id, "active_use", handler)
    actor = {"class_features": [feature_id]}

    assert available_features(actor, "active_use") == [feature_id]
    result = run_feature(feature_id, "active_use", FeatureContext(actor=actor, payload={"amount": 1}))

    assert result.lines == ["ok"]
    assert result.update["seen"] == {"amount": 1}


def test_use_class_feature_lists_available_features():
    """工具应在不指定特性时，返回当前触发点可用清单。"""
    feature_id = "test_feature_listable"

    def handler(context: FeatureContext) -> FeatureResult:
        return FeatureResult(lines=["ok"], update={})

    register_feature(feature_id, "active_use", handler)

    result = use_class_feature.func(
        feature_id="",
        trigger="active_use",
        state={"player": {"name": "Test Fighter", "class_features": [feature_id]}},
        tool_call_id="call-test-list",
    )

    assert feature_id in result.update["messages"][0].content


def test_use_class_feature_dispatches_registered_handler():
    """工具应把已注册特性转给 registry 处理，并把结果回写到状态。"""
    feature_id = "test_feature_use"

    def handler(context: FeatureContext) -> FeatureResult:
        return FeatureResult(lines=["used"], update={"feature_result": context.payload})

    register_feature(feature_id, "active_use", handler)

    result = use_class_feature.func(
        feature_id=feature_id,
        trigger="active_use",
        payload={"times": 1},
        state={"player": {"name": "Test Fighter", "class_features": [feature_id]}},
        tool_call_id="call-test-use",
    )

    assert result.update["feature_result"] == {"times": 1}
    assert "used" in result.update["messages"][0].content

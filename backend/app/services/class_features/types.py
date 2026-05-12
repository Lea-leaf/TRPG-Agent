"""职业特性框架的通用类型。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

FeatureTrigger = Literal[
    "before_attack_roll",
    "after_attack_roll",
    "on_attack_hit",
    "before_damage_roll",
    "on_damage_taken",
    "on_turn_start",
    "on_turn_end",
    "on_reaction",
    "active_use",
]


@dataclass(slots=True)
class FeatureContext:
    """职业特性的统一执行上下文。"""

    actor: dict[str, Any]
    target: dict[str, Any] | None = None
    state: dict[str, Any] | None = None
    payload: dict[str, Any] | None = None
    roll_info: dict[str, Any] | None = None


@dataclass(slots=True)
class FeatureResult:
    """职业特性执行后的统一返回值。"""

    lines: list[str]
    update: dict[str, Any]

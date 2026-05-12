"""勇士职业特性。"""

from __future__ import annotations


CHAMPION_FEATURE_IDS: tuple[str, ...] = ("improved_critical",)


def improved_critical_threshold(actor: dict, base: int = 20) -> int:
    """勇士将武器重击阈值压到 19。"""
    if "improved_critical" in actor.get("class_features", []):
        return min(base, 19)
    return base

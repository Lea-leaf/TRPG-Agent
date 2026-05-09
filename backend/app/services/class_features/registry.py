"""职业特性注册表。"""

from __future__ import annotations

from collections.abc import Callable

from app.services.class_features.champion import improved_critical_threshold
from app.services.class_features.types import FeatureContext, FeatureResult, FeatureTrigger

FeatureHandler = Callable[[FeatureContext], FeatureResult]

_REGISTRY: dict[str, dict[FeatureTrigger, FeatureHandler]] = {}


def register_feature(feature_id: str, trigger: FeatureTrigger, handler: FeatureHandler) -> FeatureHandler:
    """注册一个职业特性处理器。"""
    _REGISTRY.setdefault(feature_id, {})[trigger] = handler
    return handler


def run_feature(feature_id: str, trigger: FeatureTrigger, context: FeatureContext) -> FeatureResult:
    """执行已注册的职业特性。"""
    handler = _REGISTRY[feature_id][trigger]
    return handler(context)


def available_features(actor: dict, trigger: FeatureTrigger) -> list[str]:
    """列出当前角色在指定触发点可用的职业特性。"""
    features = actor.get("class_features", [])
    return [feature_id for feature_id in features if trigger in _REGISTRY.get(feature_id, {})]


def get_critical_threshold(actor: dict, base: int = 20) -> int:
    """按职业特性计算当前武器攻击的重击阈值。"""
    return improved_critical_threshold(actor, base)

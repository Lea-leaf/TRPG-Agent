"""冒险节点读取 — 优先使用 PDF 解析产物，缺失时回退到最小内置开局。"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from app.adventures.models import AdventureExit, AdventureNode

BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_ADVENTURE_DIR = BACKEND_DIR / "data" / "adventures" / "lost_mine"


class AdventureStore:
    """按 ID 读取冒险节点，避免工具层关心文件格式。"""

    def __init__(self, data_dir: Path = DEFAULT_ADVENTURE_DIR) -> None:
        self._data_dir = data_dir
        self._nodes = self._load_nodes()
        self._candidate_nodes = self._load_candidate_nodes()

    def get_node(self, node_id: str) -> AdventureNode:
        if node_id in self._candidate_nodes:
            candidate = self._candidate_nodes[node_id]
            if node_id in self._nodes:
                return _merge_node(self._nodes[node_id], candidate)
            return candidate
        if node_id in self._nodes:
            return self._nodes[node_id]
        else:
            raise KeyError(f"未知冒险节点: {node_id}")

    def list_nodes(self) -> list[AdventureNode]:
        merged = dict(self._nodes)
        for node_id, candidate in self._candidate_nodes.items():
            merged[node_id] = _merge_node(merged[node_id], candidate) if node_id in merged else candidate
        return list(merged.values())

    def search_nodes(self, query: str, limit: int = 5) -> list[tuple[AdventureNode, float]]:
        """按玩家意图或地点/NPC/线索检索候选剧情节点。"""
        query = query.strip()
        if not query:
            return []

        tokens = _query_tokens(query)
        scored: list[tuple[AdventureNode, float]] = []
        for node in self.list_nodes():
            score = _score_node(node, query, tokens)
            if score > 0:
                scored.append((node, score))

        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:limit]

    def _load_nodes(self) -> dict[str, AdventureNode]:
        nodes_path = self._data_dir / "nodes.json"
        if not nodes_path.exists():
            return _fallback_nodes()

        with nodes_path.open("r", encoding="utf-8") as file:
            raw_nodes = json.load(file)

        nodes = [AdventureNode.model_validate(item) for item in raw_nodes]
        return {node.id: node for node in nodes}

    def _load_candidate_nodes(self) -> dict[str, AdventureNode]:
        candidate_path = self._data_dir / "nodes.candidate.json"
        if not candidate_path.exists():
            return {}

        with candidate_path.open("r", encoding="utf-8") as file:
            raw_nodes = json.load(file)

        nodes = [AdventureNode.model_validate(item) for item in raw_nodes]
        return {node.id: node for node in nodes}


def _query_tokens(query: str) -> list[str]:
    """抽取轻量检索词；中文短语保留整段并补 2 字 gram。"""
    lowered = query.lower()
    tokens = re.findall(r"[a-z0-9_-]{2,}|[\u4e00-\u9fff]{2,}", lowered)
    grams: list[str] = []
    for token in tokens:
        if re.fullmatch(r"[\u4e00-\u9fff]{3,}", token):
            grams.extend(token[index:index + 2] for index in range(len(token) - 1))
    dedup: list[str] = []
    for token in [lowered, *tokens, *grams]:
        token = token.strip()
        if token and token not in dedup:
            dedup.append(token)
    return dedup


def _merge_node(base: AdventureNode, candidate: AdventureNode) -> AdventureNode:
    """候选节点补 PDF 细节，正式节点继续提供人工确认过的硬出口。"""
    payload = candidate.model_dump()
    if not payload.get("exits"):
        payload["exits"] = [item.model_dump() for item in base.exits]
    return AdventureNode.model_validate(payload)


def _score_node(node: AdventureNode, query: str, tokens: list[str]) -> float:
    """简单可解释的本地检索评分，避免为了小语料引入新索引。"""
    title = node.title.lower()
    node_id = node.id.lower()
    body = " ".join(
        [
            node.source_excerpt,
            node.source_text,
            node.dm_summary,
            node.player_visible_intro,
            " ".join(str(item) for item in node.clues),
            " ".join(str(item) for item in node.encounters),
            " ".join(str(item) for item in node.rewards),
            " ".join(str(item) for item in node.subsections),
            " ".join(str(item) for values in node.dm_guidance.values() for item in values),
        ]
    ).lower()

    score = 0.0
    query_lower = query.lower().strip()
    if query_lower and query_lower in title:
        score += 8
    if query_lower and query_lower in node_id:
        score += 6
    if query_lower and query_lower in body:
        score += 3

    for token in tokens:
        if token in title:
            score += 4
        if token in node_id:
            score += 3
        if token in body:
            score += 1
    return score


def _fallback_nodes() -> dict[str, AdventureNode]:
    """内置极小节点集只用于开发兜底，正式内容应来自 PDF 解析。"""
    nodes = [
        AdventureNode(
            id="lost_mine_start",
            title="第1部分：地精箭头 - 护送补给",
            kind="scene",
            page_start=6,
            page_end=6,
            source_excerpt="冒险开始，玩家们驾驶着一辆满载补给的货车从无冬城前往凡达林。",
            dm_summary=(
                "玩家受雇护送一车补给前往凡达林。当前重点是建立旅途、委托人与目的地，"
                "并把玩家自然带向三猪小径上的第一处异常。"
            ),
            player_visible_intro=(
                "你们驾驶着满载补给的货车离开无冬城，沿大路南下，又转入通往凡达林的三猪小径。"
                "离目的地还有半天路程，路旁林影渐密，车轮压过泥土与碎石。"
            ),
            exits=[
                AdventureExit(
                    id="continue_to_ambush",
                    label="继续沿三猪小径前进",
                    next_node_id="goblin_ambush",
                    description="玩家继续赶路，进入地精伏击场景。",
                )
            ],
        ),
        AdventureNode(
            id="goblin_ambush",
            title="地精伏击",
            kind="encounter",
            page_start=6,
            page_end=8,
            parent_id="lost_mine_start",
            source_excerpt="还有半天路程到达凡达林时，他们遭遇了克拉摩部族的地精劫掠者。",
            dm_summary=(
                "道路上的异常引出克拉摩地精伏击。主持时先让玩家有机会观察、调查或接近，"
                "若触发冲突，再建立战斗地图并生成地精。"
            ),
            player_visible_intro="前方道路被异样的静默压住，货车的马匹开始不安地踏步。",
            encounters=[
                {
                    "id": "goblin_ambush_goblins",
                    "monster_slug": "goblin",
                    "count": 4,
                    "trigger": "玩家进入伏击范围或主动搜索道路异常。",
                }
            ],
            clues=[
                {
                    "id": "goblin_trail",
                    "label": "地精踪迹",
                    "description": "玩家调查伏击现场后，可以发现通向克拉摩窝点的踪迹。",
                }
            ],
            events=["goblin_ambush_resolved"],
            exits=[
                AdventureExit(
                    id="follow_goblin_trail",
                    label="追踪地精踪迹",
                    next_node_id="cragmaw_hideout_entrance",
                    requires=["goblin_trail"],
                    description="玩家找到并选择追踪地精留下的路线。",
                ),
                AdventureExit(
                    id="continue_to_phandalin",
                    label="继续前往凡达林",
                    next_node_id="phandalin_arrival",
                    description="玩家暂不追踪地精，继续完成补给护送。",
                ),
            ],
        ),
        AdventureNode(
            id="cragmaw_hideout_entrance",
            title="克拉摩窝点入口",
            kind="location",
            page_start=7,
            page_end=8,
            parent_id="goblin_ambush",
            source_excerpt="俘虏地精还可能被说服而给玩家带路，一路避开陷阱直达克拉摩窝点。",
            dm_summary="玩家抵达克拉摩窝点外侧。这里应进入洞穴探索、陷阱与守卫处理。",
            player_visible_intro="地精留下的痕迹把你们带向林中溪谷，一处隐蔽洞口藏在灌木和岩石后。",
        ),
        AdventureNode(
            id="phandalin_arrival",
            title="抵达凡达林",
            kind="scene",
            page_start=7,
            page_end=7,
            parent_id="goblin_ambush",
            source_excerpt="玩家也有可能错过地精踪迹，或者打算直接前往凡达林。这时直接跳到第2部分“凡达林”。",
            dm_summary="玩家抵达凡达林，但甘德伦未按时到达的事实会把主线压力重新推回地精袭击。",
            player_visible_intro="凡达林的屋顶出现在路尽头。补给车终于抵达，但委托人却没有如约在镇上等候。",
        ),
    ]
    return {node.id: node for node in nodes}


@lru_cache(maxsize=1)
def get_adventure_store() -> AdventureStore:
    """缓存冒险数据，避免每轮工具调用重复读 JSON。"""
    return AdventureStore()

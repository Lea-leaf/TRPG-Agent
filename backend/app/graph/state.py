# backend/app/graph/state.py
from typing import Annotated, Literal, Optional, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


# 角色六维能力值（通常用于检定基础值）
AbilityBlock = TypedDict(
    "AbilityBlock",
    {
        "str": int,
        "dex": int,
        "con": int,
        "int": int,
        "wis": int,
        "cha": int,
    },
    total=False,
)

# 六维对应修正值（通常由能力值推导）
ModifierBlock = TypedDict(
    "ModifierBlock",
    {
        "str": int,
        "dex": int,
        "con": int,
        "int": int,
        "wis": int,
        "cha": int,
    },
    total=False,
)


# 玩家常驻状态
class PlayerState(TypedDict, total=False):
    name: str
    role_class: str
    level: int
    hp: int
    max_hp: int
    temp_hp: int
    ac: int
    abilities: AbilityBlock
    modifiers: ModifierBlock
    conditions: list[str]          # e.g. ["poisoned", "prone"]
    resources: dict[str, int]      # e.g. {"spell_slot_lv1": 2}


# 待执行的一次检定请求
class CheckState(TypedDict, total=False):
    kind: Literal["attack", "skill", "save", "custom"]
    ability: Literal["str", "dex", "con", "int", "wis", "cha"]
    dc: int
    target: Optional[str]
    advantage: Literal["normal", "advantage", "disadvantage"]


# 最近一次掷骰结果
class RollResultState(TypedDict, total=False):
    dice: str                      # e.g. "1d20"
    raw: int
    modifier: int
    total: int
    success: bool


# 战斗单位快照（玩家/敌人/友方）
class CombatantState(TypedDict, total=False):
    id: str
    name: str
    side: Literal["player", "enemy", "ally"]
    hp: int
    max_hp: int
    ac: int
    initiative: int
    speed: int
    conditions: list[str]

    # 动作资源
    action_available: bool                   # 标准动作
    bonus_action_available: bool             # 附赠动作
    reaction_available: bool                 # 反应
    movement_left: int                       # 剩余移动力（尺）


# 战斗对局整体状态（扁平化动作经济管理）
class CombatState(TypedDict, total=False):
    round: int                               # 当前回合数
    participants: dict[str, CombatantState]  # 参战方字典，使用 id 作为键
    initiative_order: list[str]              # 行动顺序 (按 id)
    current_actor_id: str                    # 当前回合活跃的单位 id


# 整个 LangGraph 在节点间传递的共享状态
class GraphState(TypedDict, total=False):
    # --- 核心对话流程字段 ---
    messages: Annotated[list[AnyMessage], add_messages]
    output: str

    conversation_summary: str          # 持久的大纲记忆
    session_id: str                    # 会话唯一标识

    # --- 扩展领域字段（当前 chat 主链路未启用） ---
    phase: Literal["exploration", "combat", "resolution"]

    scene_summary: str             # 场景摘要，减少长上下文重复
    player: PlayerState

    pending_check: Optional[CheckState]      # 等待掷骰解析的检定
    last_roll: Optional[RollResultState]     # 最近一次检定/攻击结果

    combat: Optional[CombatState]  # 战斗上下级聚合

    event_log: list[dict]          # 记录关键事件，便于回放/调试

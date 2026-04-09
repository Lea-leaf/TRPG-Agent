import json
import os
import uuid
import re
from typing import Optional

from app.graph.state import CombatantState
from app.calculation.dice import roll_with_notation

# 定位怪物图鉴文件路径
BESTIARY_FILE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "bestiary.json")

def get_monster_template(index: str) -> Optional[dict]:
    """
    根据怪物 index 获取官方 JSON 数据结构
    """
    if not os.path.exists(BESTIARY_FILE_PATH):
        return None
    
    with open(BESTIARY_FILE_PATH, "r", encoding="utf-8") as f:
        bestiary_data = json.load(f)
        
    for monster in bestiary_data:
        if monster.get("index") == index:
            return monster
            
    return None

def extract_speed(speed_dict: dict) -> int:
    """提取怪物步速信息并提取数字。默认为30"""
    walk_speed = speed_dict.get("walk", "30 ft.")
    match = re.search(r"(\d+)", walk_speed)
    if match:
        return int(match.group(1))
    return 30

def extract_ac(armor_class_list: list) -> int:
    """从 armor_class 数组中提取有效的 AC 值"""
    if armor_class_list and isinstance(armor_class_list, list) and len(armor_class_list) > 0:
        # 取首个 AC 对象的 value
        return armor_class_list[0].get("value", 10)
    return 10

def spawn_combatants(index: str, count: int = 1, side: str = "enemy") -> list[CombatantState]:
    """
    根据图鉴 index 生成数量为 count 的战斗单元实例列表。
    利用原生的结构动态求出其 HP、AC 和速度等战斗属性。
    """
    template = get_monster_template(index)
    if not template:
        raise ValueError(f"Monster with index '{index}' not found in bestiary.")
        
    base_name = template.get("name", "Unknown Creature")
    base_ac = extract_ac(template.get("armor_class", []))
    base_speed = extract_speed(template.get("speed", {}))
    hp_roll_notation = template.get("hit_points_roll")
    fixed_hp = template.get("hit_points", 10)
    
    combatants = []
    
    for i in range(1, count + 1):
        # 如果只生成1个就不带数字后缀，生成多个带 1, 2, 3
        name_suffix = f" {i}" if count > 1 else ""
        combatant_name = f"{base_name}{name_suffix}"
        
        # 通过掷骰生成浮动 HP
        try:
            if hp_roll_notation:
                hp_result = roll_with_notation(hp_roll_notation)
                max_hp = hp_result["total"]
            else:
                max_hp = fixed_hp
        except Exception:
            # 解析或投骰失败则降级兜底为固定值
            max_hp = fixed_hp
            
        combatant: CombatantState = {
            "id": f"{index}_{uuid.uuid4().hex[:6]}",
            "name": combatant_name,
            "side": side,
            "hp": max_hp,
            "max_hp": max_hp,
            "ac": base_ac,
            "initiative": 0, # 初始化时先不掷先攻，等到进入战斗时统一掷
            "speed": base_speed,
            "conditions": [],
            
            # 动作资源初始化全满
            "action_available": True,
            "bonus_action_available": True,
            "reaction_available": True,
            "movement_left": base_speed
        }
        combatants.append(combatant)
        
    return combatants

"""Tool definitions and execution service."""

from __future__ import annotations

import random
from functools import lru_cache

from langchain_core.tools import BaseTool, tool
from langgraph.types import interrupt


@tool
def weather(city: str, unit: str = "c") -> dict:
    """Get simple weather info for a city.

    Args:
        city: Target city name.
        unit: Temperature unit, supports "c" or "f".
    """
    normalized_unit = (unit or "c").strip().lower()
    if normalized_unit not in {"c", "f"}:
        normalized_unit = "c"

    city_name = (city or "").strip() or "unknown"
    temperature_c = 22
    temperature = temperature_c if normalized_unit == "c" else int(temperature_c * 9 / 5 + 32)

    return {
        "city": city_name,
        "temperature": temperature,
        "unit": normalized_unit,
        "condition": "clear",
        "source": "mock",
    }


@tool
def request_dice_roll(reason: str, formula: str = "1d20") -> dict:
    """Request a dice roll from the player for resolving an action (e.g., kicking a door).
    
    Args:
        reason: The narrative reason for the roll (e.g., "破门力量检定").
        formula: The dice formula (e.g., "1d20").
    """
    # 挂起 Graph 并将请求下发前端呈现按钮
    user_response = interrupt({
        "type": "dice_roll",
        "reason": reason,
        "formula": formula,
    })
    
    # 恢复执行时：如果在后端自动生成随机数
    if user_response == "confirmed":
        parts = formula.lower().split('d')
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            count, sides = int(parts[0]), int(parts[1])
            total = sum(random.randint(1, sides) for _ in range(count))
        else:
            total = random.randint(1, 20) # fallback
        return {"roll_result": total, "status": "success", "note": f"Rolled {total}."}
    
    return {"status": "failed", "note": "Player rejected the roll or unknown action."}

@lru_cache(maxsize=1)
def get_tools() -> list[BaseTool]:
    return [weather, request_dice_roll]


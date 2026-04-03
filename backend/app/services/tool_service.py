"""Tool definitions and execution service."""

from __future__ import annotations

from functools import lru_cache

from langchain_core.tools import BaseTool, tool


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


@lru_cache(maxsize=1)
def get_tools() -> list[BaseTool]:
    return [weather]


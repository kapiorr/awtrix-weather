"""Mapowanie stanu pogody HA (`weather.xxx` state) na overlay animacji AWTRIX."""
from __future__ import annotations

OVERLAY_BY_CONDITION: dict[str, str] = {
    "clear-night": "clear",
    "cloudy": "clear",
    "exceptional": "clear",
    "fog": "clear",
    "hail": "frost",
    "lightning": "thunder",
    "lightning-rainy": "thunder",
    "partlycloudy": "clear",
    "pouring": "storm",
    "rainy": "drizzle",
    "rain": "rain",
    "snowy": "snow",
    "snowy-rainy": "snow",
    "sunny": "clear",
    "windy": "clear",
    "windy-variant": "clear",
}

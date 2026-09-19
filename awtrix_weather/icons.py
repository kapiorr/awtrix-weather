"""Mapowanie stanu pogody HA (`weather.xxx` state) na overlay animacji AWTRIX.

AWTRIX NG zna tylko 6 nazw overlayów: rain, snow, drizzle, storm, thunder,
frost (patrz https://blueforcer.github.io/awtrix-ng/reference/payload/#overlay).
Nie ma odpowiednika "clear" - warunki bezchmurne/pochmurne/mgła/wiatr po
prostu nie mają wpisu w tym słowniku, więc render.py (OVERLAY_BY_CONDITION.get)
zwróci None i klucz "overlay" zostanie pominięty w payloadzie zamiast wysłać
nieznaną AWTRIX-owi wartość (co kończyło się 422 validationFailed).
"""
from __future__ import annotations

OVERLAY_BY_CONDITION: dict[str, str] = {
    "hail": "frost",
    "lightning": "thunder",
    "lightning-rainy": "thunder",
    "pouring": "storm",
    "rainy": "drizzle",
    "rain": "rain",
    "snowy": "snow",
    "snowy-rainy": "snow",
}

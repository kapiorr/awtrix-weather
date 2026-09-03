"""OpenWeatherMap - One Call API 3.0 (https://openweathermap.org/api/one-call-3).

Wymaga bezpłatnego klucza API (rejestracja na openweathermap.org). Darmowy limit
to 1000 wywołań/dzień, ale OWM przy zakładaniu konta prosi o dane karty (nie
obciąża jej w ramach darmowego limitu, ale jeśli to przeszkadza - zostań przy
Open-Meteo, które nie wymaga żadnej rejestracji).
"""
from __future__ import annotations

from datetime import datetime, timezone

import requests

from .base import CurrentWeather, ForecastPoint, WeatherData, WeatherProvider

# Mapowanie kodów warunków OWM (https://openweathermap.org/weather-conditions)
# na warunki w stylu HA.
_OWM_RANGE_MAP: list[tuple[range, str]] = [
    (range(200, 203), "lightning-rainy"),
    (range(210, 213), "lightning"),
    (range(221, 222), "lightning"),
    (range(230, 233), "lightning-rainy"),
    (range(300, 322), "rainy"),   # drizzle
    (range(500, 502), "rainy"),
    (range(502, 505), "pouring"),
    (range(511, 512), "snowy-rainy"),
    (range(520, 522), "pouring"),
    (range(522, 532), "pouring"),
    (range(600, 603), "snowy"),
    (range(611, 617), "snowy-rainy"),
    (range(620, 623), "snowy"),
    (range(701, 771), "fog"),
    (range(771, 772), "windy"),
    (range(781, 782), "windy-variant"),
]


def map_condition(owm_id: int, icon: str) -> str:
    is_day = icon.endswith("d") if icon else True

    if owm_id == 800:
        return "sunny" if is_day else "clear-night"
    if owm_id == 801 or owm_id == 802:
        return "partlycloudy"
    if owm_id in (803, 804):
        return "cloudy"

    for rng, condition in _OWM_RANGE_MAP:
        if owm_id in rng:
            return condition

    return "cloudy"


class OpenWeatherMapProvider(WeatherProvider):
    name = "openweathermap"

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("weather.openweathermap.api_key jest wymagany dla dostawcy openweathermap")
        self.api_key = api_key

    def fetch(self, lat: float, lon: float, *, units: str, timezone_name: str) -> WeatherData:
        params = {
            "lat": lat,
            "lon": lon,
            "appid": self.api_key,
            "units": units,
            "exclude": "minutely,daily,alerts",
        }
        resp = requests.get(
            "https://api.openweathermap.org/data/3.0/onecall", params=params, timeout=10
        )
        resp.raise_for_status()
        data = resp.json()

        cur_raw = data["current"]
        cur_weather = cur_raw["weather"][0]
        current = CurrentWeather(
            temperature=float(cur_raw["temp"]),
            condition=map_condition(cur_weather["id"], cur_weather.get("icon", "")),
            pressure_hpa=float(cur_raw["pressure"]) if cur_raw.get("pressure") is not None else None,
        )

        hourly: list[ForecastPoint] = []
        for entry in data.get("hourly", []):
            w = entry["weather"][0]
            hourly.append(
                ForecastPoint(
                    time=datetime.fromtimestamp(entry["dt"], tz=timezone.utc),
                    temperature=float(entry["temp"]),
                    condition=map_condition(w["id"], w.get("icon", "")),
                )
            )

        return WeatherData(current=current, hourly=hourly)

"""Open-Meteo (https://open-meteo.com) - darmowe API, bez klucza, tylko lat/lon.
Domyślny dostawca pogody."""
from __future__ import annotations

from datetime import datetime

import requests

from .base import CurrentWeather, ForecastPoint, WeatherData, WeatherProvider

# Mapowanie kodów WMO (https://open-meteo.com/en/docs -> "WMO Weather interpretation codes")
# na warunki w stylu HA, zgodne z kluczami w icons.py / config.example.yaml.
_WMO_MAP: dict[int, str] = {
    0: "sunny",           # bezchmurnie (w nocy zamieniane na clear-night niżej)
    1: "sunny",           # przeważnie bezchmurnie
    2: "partlycloudy",
    3: "cloudy",
    45: "fog",
    48: "fog",
    51: "rainy",
    53: "rainy",
    55: "rainy",
    56: "snowy-rainy",
    57: "snowy-rainy",
    61: "rainy",
    63: "rainy",
    65: "pouring",
    66: "snowy-rainy",
    67: "snowy-rainy",
    71: "snowy",
    73: "snowy",
    75: "snowy",
    77: "snowy",
    80: "rainy",
    81: "rainy",
    82: "pouring",
    85: "snowy",
    86: "snowy",
    95: "lightning",
    96: "lightning-rainy",
    99: "lightning-rainy",
}


def map_condition(weather_code: int, is_day: bool) -> str:
    condition = _WMO_MAP.get(int(weather_code), "cloudy")
    if condition == "sunny" and not is_day:
        return "clear-night"
    return condition


class OpenMeteoProvider(WeatherProvider):
    name = "open-meteo"

    def fetch(self, lat: float, lon: float, *, units: str, timezone_name: str) -> WeatherData:
        temp_unit = "fahrenheit" if units == "imperial" else "celsius"
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,weather_code,is_day,pressure_msl",
            "hourly": "temperature_2m,weather_code",
            "temperature_unit": temp_unit,
            "timezone": timezone_name or "auto",
            "forecast_days": 2,
        }
        resp = requests.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        cur = data["current"]
        current = CurrentWeather(
            temperature=float(cur["temperature_2m"]),
            condition=map_condition(cur["weather_code"], bool(cur.get("is_day", 1))),
            pressure_hpa=float(cur["pressure_msl"]) if cur.get("pressure_msl") is not None else None,
        )

        hourly_raw = data["hourly"]
        times = hourly_raw["time"]
        temps = hourly_raw["temperature_2m"]
        codes = hourly_raw["weather_code"]

        cur_time_str = cur["time"]
        start_idx = next((i for i, t in enumerate(times) if t >= cur_time_str), 0)

        hourly: list[ForecastPoint] = []
        for t, temp, code in zip(times[start_idx:], temps[start_idx:], codes[start_idx:]):
            hour = int(t[11:13])
            is_day_guess = 6 <= hour <= 20  # przybliżenie - warunek godzinowy i tak nie steruje kolorem punktu
            hourly.append(
                ForecastPoint(
                    time=datetime.fromisoformat(t),
                    temperature=float(temp),
                    condition=map_condition(code, is_day_guess),
                )
            )

        return WeatherData(current=current, hourly=hourly)

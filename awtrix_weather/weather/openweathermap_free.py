"""OpenWeatherMap - klasyczne, darmowe endpointy /data/2.5 (current weather +
5 day / 3-hour forecast). W przeciwieństwie do One Call API 3.0 (openweathermap.py)
działają z samym kluczem API bez dodatkowej subskrypcji "One Call by Call" -
przydatne, gdy dostajesz 401 z /data/3.0/onecall, a nie chcesz czekać na
aktywację subskrypcji.

Kompromis: prognoza ma rozdzielczość co 3h (nie co godzinę jak w One Call 3.0
czy Open-Meteo), więc dane godzinowe są liniowo interpolowane między punktami
co 3h - w praktyce wygląda to prawie identycznie na wyświetlaczu, ale nie jest
to prawdziwa prognoza godzinowa z API.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import requests

from .base import CurrentWeather, ForecastPoint, WeatherData, WeatherProvider
from .openweathermap import map_condition


def _interpolate_hourly(
    raw_points: list[tuple[datetime, float, str]], hours: int = 25
) -> list[ForecastPoint]:
    if not raw_points:
        return []
    raw_points.sort(key=lambda p: p[0])
    now = datetime.now(timezone.utc)

    hourly: list[ForecastPoint] = []
    for h in range(hours):
        target = now + timedelta(hours=h)
        before = None
        after = None
        for t, temp, cond in raw_points:
            if t <= target:
                before = (t, temp, cond)
            elif after is None:
                after = (t, temp, cond)
                break

        if before and after:
            span = (after[0] - before[0]).total_seconds()
            frac = (target - before[0]).total_seconds() / span if span > 0 else 0.0
            temp = before[1] + (after[1] - before[1]) * frac
            cond = before[2] if frac < 0.5 else after[2]
        elif before:
            temp, cond = before[1], before[2]
        elif after:
            temp, cond = after[1], after[2]
        else:
            continue

        hourly.append(ForecastPoint(time=target, temperature=temp, condition=cond))
    return hourly


class OpenWeatherMapFreeProvider(WeatherProvider):
    name = "openweathermap-free"

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError(
                "weather.openweathermap_api_key jest wymagany dla dostawcy openweathermap-free"
            )
        self.api_key = api_key

    def fetch(self, lat: float, lon: float, *, units: str, timezone_name: str) -> WeatherData:
        common = {"lat": lat, "lon": lon, "appid": self.api_key, "units": units}

        cur_resp = requests.get(
            "https://api.openweathermap.org/data/2.5/weather", params=common, timeout=10
        )
        cur_resp.raise_for_status()
        cur = cur_resp.json()
        cw = cur["weather"][0]
        current = CurrentWeather(
            temperature=float(cur["main"]["temp"]),
            condition=map_condition(cw["id"], cw.get("icon", "")),
            pressure_hpa=float(cur["main"]["pressure"]) if cur.get("main", {}).get("pressure") is not None else None,
        )

        fc_resp = requests.get(
            "https://api.openweathermap.org/data/2.5/forecast", params=common, timeout=10
        )
        fc_resp.raise_for_status()
        fc = fc_resp.json()

        raw_points: list[tuple[datetime, float, str]] = []
        for entry in fc.get("list", []):
            w = entry["weather"][0]
            raw_points.append(
                (
                    datetime.fromtimestamp(entry["dt"], tz=timezone.utc),
                    float(entry["main"]["temp"]),
                    map_condition(w["id"], w.get("icon", "")),
                )
            )

        return WeatherData(current=current, hourly=_interpolate_hourly(raw_points))

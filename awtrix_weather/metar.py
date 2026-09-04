"""Pobiera bieżącą temperaturę i ciśnienie ze stacji METAR przez AVWX REST API
(https://avwx.rest), jako opcjonalny "override" na dane z głównego dostawcy
pogody (weather.provider) - podmieniamy tylko liczby (temp, ciśnienie);
ikona i prognoza godzinowa zostają z głównego providera bez zmian, bo METAR
nie daje prognozy - to tylko bieżący pomiar ze stacji.

METAR aktualizuje się zwykle raz na godzinę (częściej przy nagłych zmianach -
depesze SPECI), więc cache'ujemy odczyt na tym samym interwale co główny
dostawca pogody (weather.refresh_seconds) - nie ma sensu pytać częściej.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import requests

log = logging.getLogger(__name__)

INHG_TO_HPA = 33.8639


@dataclass
class MetarReading:
    temperature_c: float | None
    pressure_hpa: float | None
    wx_description: str | None  # np. "Rain Showers", None gdy brak zjawisk (CAVOK/pogoda czysta)
    raw: str | None


def fetch_metar(station: str, api_key: str, timeout: float = 10.0) -> MetarReading:
    if not api_key:
        raise ValueError("weather.metar_override.avwx_api_key jest wymagany")
    if not station:
        raise ValueError("weather.metar_override.station jest wymagany (np. EPWA)")

    resp = requests.get(
        f"https://avwx.rest/api/metar/{station}",
        params={"format": "json"},
        headers={"Authorization": f"Token {api_key}"},
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()

    temperature_c = None
    temp_obj = data.get("temperature")
    if isinstance(temp_obj, dict) and temp_obj.get("value") is not None:
        temperature_c = float(temp_obj["value"])

    pressure_hpa = None
    alt_obj = data.get("altimeter")
    if isinstance(alt_obj, dict) and alt_obj.get("value") is not None:
        alt_value = float(alt_obj["value"])
        alt_unit = str((data.get("units") or {}).get("altimeter", "hPa")).lower()
        pressure_hpa = alt_value * INHG_TO_HPA if alt_unit in ("inhg", "in") else alt_value

    wx_description = None
    wx_codes = data.get("wx_codes")
    if isinstance(wx_codes, list) and wx_codes:
        parts = []
        for code in wx_codes:
            if isinstance(code, dict):
                parts.append(str(code.get("value") or code.get("repr") or "").strip())
            elif isinstance(code, str):
                parts.append(code)
        parts = [p for p in parts if p]
        if parts:
            wx_description = ", ".join(parts)

    return MetarReading(
        temperature_c=temperature_c,
        pressure_hpa=pressure_hpa,
        wx_description=wx_description,
        raw=data.get("raw"),
    )


class CachingMetarReader:
    """Cache'uje odczyt METAR na `refresh_seconds` (dzielone z głównym
    dostawcą pogody - `weather.refresh_seconds`), tak jak CachingWeatherProvider."""

    def __init__(self, station: str, api_key: str, refresh_seconds: int):
        self.station = station
        self.api_key = api_key
        self.refresh_seconds = max(1, refresh_seconds)
        self._cached: MetarReading | None = None
        self._cached_at: float = 0.0

    def read(self) -> MetarReading:
        now = time.monotonic()
        stale = self._cached is None or (now - self._cached_at) >= self.refresh_seconds
        if stale:
            reading = fetch_metar(self.station, self.api_key)
            self._cached = reading
            self._cached_at = now
            log.info(
                "Pobrano METAR %s: temp=%s°C, ciśnienie=%s hPa, zjawiska=%s (%s)",
                self.station,
                reading.temperature_c,
                round(reading.pressure_hpa, 1) if reading.pressure_hpa is not None else None,
                reading.wx_description or "brak",
                reading.raw,
            )
        return self._cached


def build_wx_payload(wx_description: str | None, message_duration: int) -> dict:
    """Payload dla osobnej appki z bieżącymi zjawiskami pogodowymi z METAR-u
    (np. "Rain Showers", "Thunderstorm"). Pusty {} gdy nic do zgłoszenia -
    to jedyny sposób, żeby AWTRIX skasował poprzedni komunikat (patrz appka
    wschodu/zachodu słońca - ten sam mechanizm)."""
    if not wx_description:
        return {}
    return {
        "text": wx_description,
        "color": "#F2A93B",  # bursztynowy - wizualnie "ostrzegawczy"
        "duration": message_duration,
        "pushIcon": 2,
        "lifetime": 120,
        "lifetimeMode": 1,
    }

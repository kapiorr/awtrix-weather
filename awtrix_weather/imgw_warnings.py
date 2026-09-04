"""Ostrzeżenia meteorologiczne IMGW-PIB dla wybranego powiatu (kod TERYT),
z nieoficjalnego, ale publicznie dostępnego endpointu JSON stojącego za
serwisem meteo.imgw.pl (ten sam, z którego korzysta oficjalna strona i kilka
integracji Home Assistant). Bez klucza API, bez limitu zapytań.

Endpoint zwraca WSZYSTKIE aktywne ostrzeżenia w Polsce naraz + mapę
kod_TERYT -> lista ID ostrzeżeń - filtrujemy po naszej stronie do jednego
powiatu.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import requests

log = logging.getLogger(__name__)

WARNINGS_URL = "https://meteo.imgw.pl/api/meteo/messages/v1/osmet/latest/osmet-teryt"

# Oficjalna paleta kolorów ostrzeżeń IMGW (1=żółty, 2=pomarańczowy, 3=czerwony)
LEVEL_COLORS = {1: "#FFD500", 2: "#FF8C00", 3: "#E30000"}
DEFAULT_COLOR = "#FFD500"


@dataclass
class Warning:
    phenomenon_name: str
    phenomenon_code: str
    level: int
    valid_from: str | None  # ISO8601, np. "2026-09-04T19:06:00+02:00"
    valid_to: str | None
    content: str


def fetch_warnings(teryt: str, timeout: float = 10.0) -> list[Warning]:
    resp = requests.get(WARNINGS_URL, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()

    warning_ids = data.get("teryt", {}).get(teryt, [])
    warnings_raw = data.get("warnings", {})

    result: list[Warning] = []
    for wid in warning_ids:
        w = warnings_raw.get(wid)
        if not w:
            continue
        try:
            level = int(w.get("Level") or 0)
        except (TypeError, ValueError):
            level = 0
        result.append(
            Warning(
                phenomenon_name=w.get("PhenomenonName", "").strip(),
                phenomenon_code=w.get("PhenomenonCode", "").strip(),
                level=level,
                valid_from=w.get("LxValidFrom"),
                valid_to=w.get("LxValidTo"),
                content=w.get("Content", "").strip(),
            )
        )
    return result


class CachingImgwWarningsReader:
    def __init__(self, teryt: str, refresh_seconds: int):
        self.teryt = teryt
        self.refresh_seconds = max(1, refresh_seconds)
        self._cached: list[Warning] | None = None
        self._cached_at: float = 0.0

    def read(self) -> list[Warning]:
        now = time.monotonic()
        stale = self._cached is None or (now - self._cached_at) >= self.refresh_seconds
        if stale:
            warnings = fetch_warnings(self.teryt)
            self._cached = warnings
            self._cached_at = now
            if warnings:
                summary = ", ".join(f"{w.phenomenon_name}/{w.level}" for w in warnings)
                log.info("Pobrano ostrzeżenia IMGW dla %s: %s", self.teryt, summary)
            else:
                log.info("Pobrano ostrzeżenia IMGW dla %s: brak aktywnych", self.teryt)
        return self._cached


def _pick_most_severe(warnings: list[Warning]) -> Warning | None:
    if not warnings:
        return None
    return max(warnings, key=lambda w: w.level)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def filter_currently_active(warnings: list[Warning], now: datetime | None = None) -> list[Warning]:
    """Zostawia tylko ostrzeżenia, dla których `now` mieści się w przedziale
    ValidFrom..ValidTo. IMGW czasem publikuje ostrzeżenia z wyprzedzeniem
    (ValidFrom w przyszłości) - takie pomijamy, dopóki faktycznie nie
    wejdą w życie. Ostrzeżenie bez poprawnych dat ważności jest pomijane
    (bezpieczniej nic nie pokazać niż pokazać coś na stałe)."""
    now = now or datetime.now(timezone.utc)
    active = []
    for w in warnings:
        valid_from = _parse_dt(w.valid_from)
        valid_to = _parse_dt(w.valid_to)
        if valid_from is None or valid_to is None:
            log.debug("Pomijam ostrzeżenie %s - brak poprawnych dat ważności", w.phenomenon_name)
            continue
        if valid_from <= now <= valid_to:
            active.append(w)
    return active


def build_alert_payload(warnings: list[Warning], message_duration: int, now: datetime | None = None) -> dict:
    """Pusty {} gdy brak AKTUALNIE obowiązujących ostrzeżeń dla powiatu (albo
    wszystkie już wygasły, albo jeszcze się nie zaczęły) - to jedyny sposób,
    żeby AWTRIX skasował poprzedni komunikat (ten sam mechanizm co appka
    wschodu/zachodu słońca i zjawisk z METAR-u)."""
    active = filter_currently_active(warnings, now)
    top = _pick_most_severe(active)
    if top is None:
        return {}

    color = LEVEL_COLORS.get(top.level, DEFAULT_COLOR)
    text = f"{top.phenomenon_name} /{top.level}" if top.phenomenon_name else f"Ostrzeżenie /{top.level}"

    return {
        "text": text,
        "color": color,
        "duration": message_duration,
        "pushIcon": 2,
        "lifetime": 120,
        "lifetimeMode": 1,
    }

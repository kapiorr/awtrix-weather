"""Trend ciśnienia (rośnie/spada/stabilne) liczony z własnej historii odczytów
- żaden z dostawców pogody nie zwraca "trendu" wprost, więc porównujemy
aktualny odczyt z odczytem sprzed `trend_window_hours` z naszej pamięci.

Przy starcie skryptu (pusta historia) trend jest nieznany, dopóki historia nie
sięgnie wstecz przynajmniej `trend_window_hours` - do tego czasu pokazujemy
"steady" (bez strzałki) zamiast zgadywać.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .config import PressureConfig

STEADY_THRESHOLD_HPA = 1.0  # mniejsza zmiana niż to w oknie czasu = "steady"


@dataclass
class PressureReading:
    at: datetime
    hpa: float


class PressureTrendTracker:
    def __init__(self, window_hours: float, max_age_hours: float = 12.0):
        self.window_hours = window_hours
        self.max_age = timedelta(hours=max_age_hours)
        self._history: deque[PressureReading] = deque()

    def record(self, hpa: float, at: datetime | None = None) -> None:
        at = at or datetime.now(timezone.utc)
        self._history.append(PressureReading(at=at, hpa=hpa))
        cutoff = at - self.max_age
        while self._history and self._history[0].at < cutoff:
            self._history.popleft()

    def trend(self) -> str | None:
        """"rising" | "falling" | "steady" | None (za mało historii jeszcze)."""
        if not self._history:
            return None
        now = self._history[-1].at
        target = now - timedelta(hours=self.window_hours)

        # najstarszy odczyt, który jest >= target (najbliższy oknu od dołu)
        reference = None
        for reading in self._history:
            if reading.at <= target:
                reference = reading
            else:
                break

        if reference is None:
            # historia jeszcze nie sięga wstecz na tyle - za wcześnie na trend
            if (now - self._history[0].at) < timedelta(hours=self.window_hours * 0.5):
                return None
            reference = self._history[0]

        delta = self._history[-1].hpa - reference.hpa
        if abs(delta) < STEADY_THRESHOLD_HPA:
            return "steady"
        return "rising" if delta > 0 else "falling"


TREND_SYMBOL = {"rising": "^", "falling": "v", "steady": "="}
TREND_COLOR = {"rising": "#5ECC62", "falling": "#E85C5C", "steady": "#9c9d97"}


def level_color(pressure_hpa: float, cfg: PressureConfig) -> str:
    if pressure_hpa < cfg.low_hpa:
        return cfg.low_color
    if pressure_hpa > cfg.high_hpa:
        return cfg.high_color
    return cfg.normal_color


def build_pressure_payload(pressure_hpa: float, trend: str | None, cfg: PressureConfig) -> dict:
    number_color = level_color(pressure_hpa, cfg)
    symbol = TREND_SYMBOL.get(trend, "")
    trend_color = TREND_COLOR.get(trend, "#9c9d97")

    text_segments = [
        {"t": str(round(pressure_hpa)), "c": number_color},
        {"t": " H", "c": "#9c9d97"},
    ]
    if symbol:
        text_segments.append({"t": " " + symbol, "c": trend_color})

    return {
        "text": text_segments,
        "duration": cfg.message_duration,
        "pushIcon": 2,
        "lifetime": 120,
        "lifetimeMode": 1,
    }

"""Cache'uje wynik providera pogody między cyklami głównej pętli, żeby nie
odpytywać API co `poll_interval_seconds` (domyślnie 60s), tylko rzadziej -
`weather.refresh_seconds` (domyślnie 300s = 5 min). Prognoza godzinowa i tak
nie zmienia się co minutę, a przy OpenWeatherMap (limit 1000 zapytań/dzień)
odpytywanie co 60s przekracza darmowy limit (1440/dzień)."""
from __future__ import annotations

import logging
import time

from .base import WeatherData, WeatherProvider

log = logging.getLogger(__name__)


class CachingWeatherProvider(WeatherProvider):
    def __init__(self, inner: WeatherProvider, refresh_seconds: int):
        self.inner = inner
        self.name = inner.name
        self.refresh_seconds = max(1, refresh_seconds)
        self._cached: WeatherData | None = None
        self._cached_at: float = 0.0

    def fetch(self, lat: float, lon: float, *, units: str, timezone_name: str) -> WeatherData:
        now = time.monotonic()
        stale = self._cached is None or (now - self._cached_at) >= self.refresh_seconds
        if stale:
            self._cached = self.inner.fetch(lat, lon, units=units, timezone_name=timezone_name)
            self._cached_at = now
            log.info(
                "Pobrano dane pogodowe z %s: temp=%.1f°, warunek=%s",
                self.inner.name,
                self._cached.current.temperature,
                self._cached.current.condition,
            )
        else:
            log.debug(
                "Używam danych pogodowych z cache (odśwież za %.0fs)",
                self.refresh_seconds - (now - self._cached_at),
            )
        return self._cached

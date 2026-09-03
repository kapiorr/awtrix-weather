"""Wspólny interfejs dla dostawców pogody. Normalizujemy warunek pogodowy do
tego samego zestawu, co używała integracja `weather` w Home Assistant, żeby
mapowanie na ikony/overlay (icons.py) zostało bez zmian:

  clear-night, cloudy, exceptional, fog, hail, lightning, lightning-rainy,
  partlycloudy, pouring, rainy, snowy, snowy-rainy, sunny, windy, windy-variant
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ForecastPoint:
    time: datetime
    temperature: float
    condition: str


@dataclass
class CurrentWeather:
    temperature: float
    condition: str
    pressure_hpa: float | None = None


@dataclass
class WeatherData:
    current: CurrentWeather
    hourly: list[ForecastPoint]  # posortowane rosnąco, zaczynając od "teraz"


class WeatherProvider(ABC):
    name: str = "base"

    @abstractmethod
    def fetch(self, lat: float, lon: float, *, units: str, timezone_name: str) -> WeatherData:
        """units: 'metric' lub 'imperial'."""
        raise NotImplementedError

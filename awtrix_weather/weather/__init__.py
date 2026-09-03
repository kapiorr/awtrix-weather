from __future__ import annotations

from .base import WeatherProvider
from .open_meteo import OpenMeteoProvider
from .openweathermap import OpenWeatherMapProvider
from .openweathermap_free import OpenWeatherMapFreeProvider


def create_provider(provider_name: str, *, openweathermap_api_key: str = "") -> WeatherProvider:
    if provider_name == "open-meteo":
        return OpenMeteoProvider()
    if provider_name == "openweathermap":
        return OpenWeatherMapProvider(openweathermap_api_key)
    if provider_name == "openweathermap-free":
        return OpenWeatherMapFreeProvider(openweathermap_api_key)
    raise ValueError(
        f"Nieznany dostawca pogody: {provider_name!r} "
        "(dozwolone: open-meteo, openweathermap, openweathermap-free)"
    )

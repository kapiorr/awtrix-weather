"""Wczytywanie konfiguracji z pliku YAML + override przez zmienne środowiskowe.

Sekrety (klucz OpenWeatherMap, hasło MQTT) najwygodniej trzymać w env, nie w pliku:
  OWM_API_KEY, MQTT_HOST, MQTT_PORT, MQTT_USERNAME, MQTT_PASSWORD
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import yaml


@dataclass
class LocationConfig:
    latitude: float
    longitude: float
    elevation: float = 0.0
    timezone: str = ""  # IANA tz, np. "Europe/Warsaw"; puste = strefa systemowa


@dataclass
class MetarOverrideConfig:
    enabled: bool = False
    station: str = ""       # kod ICAO stacji, np. "EPWA"
    avwx_api_key: str = ""
    refresh_seconds: int = 900  # osobny interwał od weather.refresh_seconds


@dataclass
class WeatherConfig:
    provider: str = "open-meteo"  # open-meteo | openweathermap
    openweathermap_api_key: str = ""
    units: str = "metric"  # metric | imperial
    refresh_seconds: int = 300  # jak często realnie odpytywać API pogodowe (cache między) - dotyczy też METAR-u
    hours_to_show: int = 12
    temp_digits: int = 0
    temp_suffix: str = "°"
    color_matrix: dict[float, str] = field(default_factory=dict)
    icons: dict[str, str] = field(default_factory=dict)
    show_overlay: bool = True
    message_duration_forecast: int = 30
    metar_override: MetarOverrideConfig = field(default_factory=MetarOverrideConfig)


@dataclass
class MoonConfig:
    enabled: bool = True
    when_show: str = "night"  # never|always|risen|night
    use_moon_for_clear_night: bool = True
    use_moon_for_sunny_night: bool = True


@dataclass
class SunConfig:
    show_rise_set: bool = True
    event_minute_threshold: int = 30
    time_type: str = "Actual"  # Actual|Relative
    time_format: str = "%-I%M%p"
    message_duration: int = 30


@dataclass
class PressureConfig:
    enabled: bool = False
    app_topic: str = "jeef_pressure"
    trend_window_hours: float = 3.0
    message_duration: int = 30
    low_hpa: float = 1000.0
    high_hpa: float = 1020.0
    low_color: str = "#4FA8E8"    # niebieski - niskie ciśnienie
    normal_color: str = "#FFFFFF"  # biały - normalne
    high_color: str = "#F2A93B"    # bursztynowy - wysokie ciśnienie


@dataclass
class MqttConfig:
    host: str = "127.0.0.1"
    port: int = 1883
    username: str = ""
    password: str = ""
    client_id: str = "awtrix-weather"


@dataclass
class HttpConfig:
    port: int = 80
    timeout: float = 5.0
    use_https: bool = False


@dataclass
class AwtrixConfig:
    transport: str = "http"  # http | mqtt
    app_topic: str = "jeef_weather"
    devices: list[str] = field(default_factory=list)  # http: IP/hostname, mqtt: base topic
    http: HttpConfig = field(default_factory=HttpConfig)
    mqtt: MqttConfig = field(default_factory=MqttConfig)
    check_icons_on_start: bool = True
    auto_upload_missing_icons: bool = False


@dataclass
class AppConfig:
    location: LocationConfig
    weather: WeatherConfig
    moon: MoonConfig
    sun: SunConfig
    pressure: PressureConfig
    awtrix: AwtrixConfig
    poll_interval_seconds: int = 60


def _env(key: str, default: str | None = None) -> str | None:
    val = os.environ.get(key)
    return val if val not in (None, "") else default


def _load_metar_override(mo_raw: dict) -> MetarOverrideConfig:
    return MetarOverrideConfig(
        enabled=bool(mo_raw.get("enabled", False)),
        station=str(mo_raw.get("station", "")).upper(),
        avwx_api_key=_env("AVWX_API_KEY", mo_raw.get("avwx_api_key", "")),
        refresh_seconds=int(mo_raw.get("refresh_seconds", 900)),
    )


def load_config(path: str) -> AppConfig:
    with open(path, "r", encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}

    loc_raw = raw.get("location", {})
    location = LocationConfig(
        latitude=float(loc_raw["latitude"]),
        longitude=float(loc_raw["longitude"]),
        elevation=float(loc_raw.get("elevation", 0.0)),
        timezone=loc_raw.get("timezone", ""),
    )

    w_raw = raw.get("weather", {})
    color_matrix = {float(k): v for k, v in w_raw.get("color_matrix", {}).items()}
    weather = WeatherConfig(
        provider=w_raw.get("provider", "open-meteo"),
        openweathermap_api_key=_env("OWM_API_KEY", w_raw.get("openweathermap_api_key", "")),
        units=w_raw.get("units", "metric"),
        refresh_seconds=int(w_raw.get("refresh_seconds", 300)),
        hours_to_show=int(w_raw.get("hours_to_show", 12)),
        temp_digits=int(w_raw.get("temp_digits", 0)),
        temp_suffix=str(w_raw.get("temp_suffix", "°")),
        color_matrix=color_matrix,
        icons=w_raw.get("icons", {}),
        show_overlay=bool(w_raw.get("show_overlay", True)),
        message_duration_forecast=int(w_raw.get("message_duration_forecast", 30)),
        metar_override=_load_metar_override(w_raw.get("metar_override", {})),
    )

    m_raw = raw.get("moon", {})
    moon = MoonConfig(
        enabled=bool(m_raw.get("enabled", True)),
        when_show=m_raw.get("when_show", "night"),
        use_moon_for_clear_night=bool(m_raw.get("use_moon_for_clear_night", True)),
        use_moon_for_sunny_night=bool(m_raw.get("use_moon_for_sunny_night", True)),
    )

    s_raw = raw.get("sun", {})
    sun = SunConfig(
        show_rise_set=bool(s_raw.get("show_rise_set", True)),
        event_minute_threshold=int(s_raw.get("event_minute_threshold", 30)),
        time_type=s_raw.get("time_type", "Actual"),
        time_format=s_raw.get("time_format", "%-I%M%p"),
        message_duration=int(s_raw.get("message_duration", 30)),
    )

    p_raw = raw.get("pressure", {})
    pressure = PressureConfig(
        enabled=bool(p_raw.get("enabled", False)),
        app_topic=p_raw.get("app_topic", "jeef_pressure"),
        trend_window_hours=float(p_raw.get("trend_window_hours", 3.0)),
        message_duration=int(p_raw.get("message_duration", 30)),
        low_hpa=float(p_raw.get("low_hpa", 1000.0)),
        high_hpa=float(p_raw.get("high_hpa", 1020.0)),
        low_color=str(p_raw.get("low_color", "#4FA8E8")),
        normal_color=str(p_raw.get("normal_color", "#FFFFFF")),
        high_color=str(p_raw.get("high_color", "#F2A93B")),
    )

    a_raw = raw.get("awtrix", {})
    http_raw = a_raw.get("http", {})
    mqtt_raw = a_raw.get("mqtt", {})
    awtrix = AwtrixConfig(
        transport=a_raw.get("transport", "http"),
        app_topic=a_raw.get("app_topic", "jeef_weather"),
        devices=a_raw.get("devices", []),
        http=HttpConfig(
            port=int(http_raw.get("port", 80)),
            timeout=float(http_raw.get("timeout", 5.0)),
            use_https=bool(http_raw.get("use_https", False)),
        ),
        mqtt=MqttConfig(
            host=_env("MQTT_HOST", mqtt_raw.get("host", "127.0.0.1")),
            port=int(_env("MQTT_PORT", str(mqtt_raw.get("port", 1883)))),
            username=_env("MQTT_USERNAME", mqtt_raw.get("username", "")),
            password=_env("MQTT_PASSWORD", mqtt_raw.get("password", "")),
            client_id=mqtt_raw.get("client_id", "awtrix-weather"),
        ),
        check_icons_on_start=bool(a_raw.get("check_icons_on_start", True)),
        auto_upload_missing_icons=bool(a_raw.get("auto_upload_missing_icons", False)),
    )

    return AppConfig(
        location=location,
        weather=weather,
        moon=moon,
        sun=sun,
        pressure=pressure,
        awtrix=awtrix,
        poll_interval_seconds=int(raw.get("poll_interval_seconds", 60)),
    )

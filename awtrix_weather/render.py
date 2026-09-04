"""Spina dane pogodowe/astronomiczne w payload JSON, jaki AWTRIX oczekuje
(na custom app `<app_topic>` i drugi, uproszczony, `<app_topic>_sun`).

To jest odpowiednik sekcji `variables:` + `action:` z oryginalnego blueprintu,
ale bez Home Assistant - dane biorą się z lokalnego dostawcy pogody (weather/)
i lokalnych obliczeń astronomicznych (astro.py).
"""
from __future__ import annotations

import logging

from .astro import get_moon_state, get_sun_state
from .color import interpolate_color
from .config import AppConfig
from .icons import OVERLAY_BY_CONDITION
from .moon import CLEAR_NIGHT_ICON_BY_PHASE, draw_moon_command
from .sun_event import compute_sun_event
from .text import center_text_x
from .weather.base import WeatherData, WeatherProvider

log = logging.getLogger(__name__)


def _should_show_moon(cfg: AppConfig, moon_risen: bool, sun_elevation: float) -> bool:
    mode = cfg.moon.when_show
    if mode == "always":
        return True
    if mode == "never":
        return False
    if mode == "risen":
        return moon_risen
    # "night" (domyślne): księżyc widoczny + słońce pod horyzontem
    return sun_elevation < 0 and moon_risen


def build_payloads(
    provider: WeatherProvider, cfg: AppConfig, metar_reader=None
) -> tuple[dict, dict, float | None, str | None]:
    w = cfg.weather
    loc = cfg.location

    weather_data: WeatherData = provider.fetch(
        loc.latitude, loc.longitude, units=w.units, timezone_name=loc.timezone
    )

    if metar_reader is not None:
        try:
            metar = metar_reader.read()
            if metar.temperature_c is not None:
                weather_data.current.temperature = metar.temperature_c
            if metar.pressure_hpa is not None:
                weather_data.current.pressure_hpa = metar.pressure_hpa
            metar_wx_description = metar.wx_description
        except Exception:
            log.warning(
                "Nie udało się pobrać METAR (%s) - używam danych z %s",
                cfg.weather.metar_override.station,
                provider.name,
                exc_info=True,
            )
            metar_wx_description = None
    else:
        metar_wx_description = None

    current_condition = weather_data.current.condition
    current_temp = weather_data.current.temperature
    forecast = weather_data.hourly

    temp_value = round(current_temp, w.temp_digits)
    temp_text = f"{temp_value}{w.temp_suffix}"
    # --- Astronomia ---
    sun_state = get_sun_state(loc.latitude, loc.longitude, loc.elevation)
    log.info(
        "Słońce: wysokość %.1f° | najbliższy wschód %s | najbliższy zachód %s",
        sun_state.elevation_deg,
        sun_state.next_rising.astimezone().strftime("%Y-%m-%d %H:%M"),
        sun_state.next_setting.astimezone().strftime("%Y-%m-%d %H:%M"),
    )

    moon_phase = None
    moon_risen = False
    if cfg.moon.enabled:
        moon_state = get_moon_state(loc.latitude, loc.longitude, loc.elevation)
        moon_phase = moon_state.phase_name
        moon_risen = moon_state.altitude_deg > 0
        log.info(
            "Księżyc: wysokość %.1f° (%s) | faza %s",
            moon_state.altitude_deg,
            "nad horyzontem" if moon_risen else "pod horyzontem",
            moon_phase,
        )

    show_moon = cfg.moon.enabled and _should_show_moon(cfg, moon_risen, sun_state.elevation_deg)

    sun_info = compute_sun_event(
        sun_state.next_rising,
        sun_state.next_setting,
        time_type=cfg.sun.time_type,
        time_format=cfg.sun.time_format,
        icon_sunrise=w.icons.get("sunrise", "w-sunrise"),
        icon_sunset=w.icons.get("sunset", "w-sunset"),
        event_minute_threshold=cfg.sun.event_minute_threshold,
        message_duration=cfg.sun.message_duration,
        show_rise_set=cfg.sun.show_rise_set,
    )
    sun_next_event = sun_info.event

    # --- Ikona główna ---
    use_moon_clear_night = cfg.moon.enabled and cfg.moon.use_moon_for_clear_night
    use_moon_sunny_night = cfg.moon.enabled and cfg.moon.use_moon_for_sunny_night

    if current_condition == "clear-night" and use_moon_clear_night and moon_phase:
        icon = CLEAR_NIGHT_ICON_BY_PHASE.get(moon_phase, w.icons.get("clear-night", ""))
        moon_x = 0
    elif sun_next_event == "sunrise" and use_moon_sunny_night and current_condition == "sunny":
        icon = ""
        moon_x = 0
    else:
        icon = w.icons.get(current_condition, "")
        moon_x = 23

    moon_cmd = None
    if show_moon and moon_phase:
        moon_cmd = draw_moon_command(moon_phase, x=moon_x, y=0)

    # --- Linia prognozy (kolorowe kropki wg temperatury) ---
    draw: list[dict] = []
    for hour, point in enumerate(forecast[: w.hours_to_show]):
        color = interpolate_color(w.color_matrix, point.temperature) or "#FFFFFF"
        draw.append({"dp": [8 + hour, 7, color]})

    # --- Aktualna temperatura (tekst) ---
    text_available_width = 16 if show_moon else 24
    text_x = center_text_x(temp_text, text_available_width)
    text_color = interpolate_color(w.color_matrix, temp_value) or "#FFFFFF"
    log.debug(
        "temp=%s (units=%s) -> kolor tekstu=%s | warunek=%s -> ikona=%s",
        temp_value, w.units, text_color, current_condition, icon,
    )
    draw.append({"dt": [text_x, 1, temp_text, text_color]})

    if moon_cmd:
        draw.append(moon_cmd)

    main_payload: dict = {
        "draw": draw,
        "icon": icon,
        "duration": w.message_duration_forecast,
        "pushIcon": 2,
        "lifetime": 120,
        "lifetimeMode": 1,
        "weather": current_condition,
    }
    if w.show_overlay:
        overlay = OVERLAY_BY_CONDITION.get(current_condition)
        if overlay:
            main_payload["overlay"] = overlay

    sun_payload = sun_info.payload if sun_info.payload else {}

    return main_payload, sun_payload, weather_data.current.pressure_hpa, metar_wx_description

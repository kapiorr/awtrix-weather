"""Budowanie komunikatu o zbliżającym się wschodzie/zachodzie słońca
(port sekcji SUN THINGS z blueprintu), na bazie danych z astro.py."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class SunEventInfo:
    event: str  # "sunrise" | "sunset"
    minutes_until: int
    display_text: object  # str albo lista segmentów rich-text (tryb Relative)
    icon: str
    payload: dict | None  # None/{} => nic nie pokazujemy


def compute_sun_event(
    next_rising: datetime,
    next_setting: datetime,
    *,
    time_type: str,
    time_format: str,
    icon_sunrise: str,
    icon_sunset: str,
    event_minute_threshold: int,
    message_duration: int,
    show_rise_set: bool,
) -> SunEventInfo:
    now = datetime.now(timezone.utc)

    event = "sunset" if next_setting < next_rising else "sunrise"
    target = next_setting if event == "sunset" else next_rising
    minutes_until = round((target - now).total_seconds() / 60)

    if time_type == "Actual":
        local_target = target.astimezone()  # strefa systemowa (ustaw TZ w Dockerze)
        display_text: object = local_target.strftime(time_format)
    else:
        hours = minutes_until // 60
        remaining_minutes = minutes_until % 60
        if hours == 0:
            display_text = f"{remaining_minutes} min"
        else:
            display_text = [
                {"t": str(hours), "c": "#ffffff"},
                {"t": "h", "c": "#9c9d97"},
                {"t": str(remaining_minutes), "c": "#ffffff"},
                {"t": "m", "c": "#9c9d97"},
            ]

    icon = icon_sunrise if event == "sunrise" else icon_sunset

    payload = None
    if show_rise_set and event_minute_threshold >= minutes_until:
        payload = {"icon": icon, "text": display_text, "duration": message_duration}

    return SunEventInfo(
        event=event,
        minutes_until=minutes_until,
        display_text=display_text,
        icon=icon,
        payload=payload,
    )

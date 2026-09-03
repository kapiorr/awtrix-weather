"""Słońce i księżyc liczone lokalnie (bez Home Assistant) za pomocą `ephem`.

Zastępuje to, co w oryginalnym blueprincie brało z encji `sun.sun` (next_rising,
next_setting, elevation) i integracji `moon` + REST sensor (moon_altitude).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone

import ephem

MOON_PHASE_NAMES = [
    "new_moon",
    "waxing_crescent",
    "first_quarter",
    "waxing_gibbous",
    "full_moon",
    "waning_gibbous",
    "last_quarter",
    "waning_crescent",
]


@dataclass
class SunState:
    elevation_deg: float
    next_rising: datetime  # UTC
    next_setting: datetime  # UTC


@dataclass
class MoonState:
    altitude_deg: float
    phase_name: str


def _make_observer(lat: float, lon: float, elevation_m: float = 0.0) -> ephem.Observer:
    obs = ephem.Observer()
    obs.lat = str(lat)
    obs.lon = str(lon)
    obs.elevation = elevation_m
    obs.date = ephem.Date(datetime.utcnow())
    return obs


def _to_utc_datetime(ephem_date: ephem.Date) -> datetime:
    return ephem_date.datetime().replace(tzinfo=timezone.utc)


def get_sun_state(lat: float, lon: float, elevation_m: float = 0.0) -> SunState:
    obs = _make_observer(lat, lon, elevation_m)
    sun = ephem.Sun(obs)
    sun.compute(obs)
    elevation_deg = math.degrees(float(sun.alt))

    next_rising = _to_utc_datetime(obs.next_rising(ephem.Sun()))
    next_setting = _to_utc_datetime(obs.next_setting(ephem.Sun()))

    return SunState(elevation_deg=elevation_deg, next_rising=next_rising, next_setting=next_setting)


def _moon_phase_name(dt: datetime) -> str:
    ed = ephem.Date(dt)
    prev_new = ephem.previous_new_moon(ed)
    next_new = ephem.next_new_moon(ed)
    cycle_length = float(next_new) - float(prev_new)
    lunar_age = float(ed) - float(prev_new)
    fraction = (lunar_age / cycle_length) % 1.0
    index = int(fraction * 8) % 8
    return MOON_PHASE_NAMES[index]


def get_moon_state(lat: float, lon: float, elevation_m: float = 0.0) -> MoonState:
    obs = _make_observer(lat, lon, elevation_m)
    moon = ephem.Moon(obs)
    moon.compute(obs)
    altitude_deg = math.degrees(float(moon.alt))
    phase_name = _moon_phase_name(datetime.utcnow())
    return MoonState(altitude_deg=altitude_deg, phase_name=phase_name)

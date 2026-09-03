"""Sprawdzenie przy starcie, czy `weather.color_matrix` pasuje skalą do
`weather.units` - typowy błąd: zostawiona skala Fahrenheita (0-100) przy
units: metric (Celsjusz), albo odwrotnie. Efekt to źle dobrany kolor tekstu
temperatury (i kropek prognozy) względem realnej wartości."""
from __future__ import annotations

import logging

from .config import AppConfig

log = logging.getLogger(__name__)


def check_color_matrix_units(cfg: AppConfig) -> None:
    matrix = cfg.weather.color_matrix
    if not matrix:
        log.warning("weather.color_matrix jest puste - kolory temperatury zawsze będą białe (#FFFFFF).")
        return

    keys = list(matrix.keys())
    lo, hi = min(keys), max(keys)

    if cfg.weather.units == "metric" and hi > 55:
        log.warning(
            "weather.color_matrix wygląda na skalę Fahrenheita (zakres %s..%s) a "
            "weather.units=metric (Celsjusz) - kolory temperatury (tekst i kropki "
            "prognozy) będą źle dobrane. Podmień color_matrix na skalę Celsjusza "
            "(przykład w README/config.example.yaml) albo ustaw units: imperial.",
            lo, hi,
        )
    elif cfg.weather.units == "imperial" and hi < 55 and lo > -30:
        log.warning(
            "weather.color_matrix wygląda na skalę Celsjusza (zakres %s..%s) a "
            "weather.units=imperial (Fahrenheit) - kolory temperatury będą źle "
            "dobrane. Podmień color_matrix na skalę Fahrenheita albo ustaw units: metric.",
            lo, hi,
        )

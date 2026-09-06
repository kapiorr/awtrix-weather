#!/usr/bin/env python3
"""Ręczne sprawdzenie ostrzeżeń meteorologicznych IMGW dla powiatu - wypisuje
WSZYSTKIE ostrzeżenia (nie tylko najsilniejsze, jak appka na AWTRIX), razem
z datami ważności, w konsoli.

Użycie:
    python check_imgw_warnings.py                      # bierze teryt z config.yaml
    python check_imgw_warnings.py --teryt 1465          # konkretny kod, bez configu
    python check_imgw_warnings.py -c inny_config.yaml
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

from awtrix_weather.config import load_config
from awtrix_weather.imgw_warnings import fetch_warnings, filter_currently_active


def _fmt(dt_str: str | None) -> str:
    if not dt_str:
        return "?"
    try:
        dt = datetime.fromisoformat(dt_str)
        return dt.strftime("%Y-%m-%d %H:%M %z")
    except ValueError:
        return dt_str


def main() -> int:
    parser = argparse.ArgumentParser(description="Sprawdź ostrzeżenia IMGW dla powiatu (konsola)")
    parser.add_argument("-c", "--config", default=os.environ.get("CONFIG_PATH", "config.yaml"))
    parser.add_argument("--teryt", help="Kod TERYT powiatu (4 znaki, np. 1465) - pomija config.yaml")
    args = parser.parse_args()

    if args.teryt:
        teryt = args.teryt.strip()
    else:
        cfg = load_config(args.config)
        teryt = cfg.imgw_warnings.teryt
        if not teryt:
            print("Brak kodu TERYT - podaj --teryt albo ustaw imgw_warnings.teryt w config.yaml", file=sys.stderr)
            return 1

    print(f"Pobieram ostrzeżenia dla powiatu {teryt}...\n")
    warnings = fetch_warnings(teryt)

    if not warnings:
        print("Brak jakichkolwiek ostrzeżeń (aktywnych lub zaplanowanych) dla tego powiatu.")
        return 0

    now = datetime.now(timezone.utc)
    active_ids = {id(w) for w in filter_currently_active(warnings, now=now)}

    for w in warnings:
        status = "AKTYWNE TERAZ" if id(w) in active_ids else "nieaktywne (przyszłość/wygasłe)"
        print(f"[{status}]")
        print(f"  Zjawisko:     {w.phenomenon_name} ({w.phenomenon_code})")
        print(f"  Poziom:       {w.level}")
        print(f"  Ważność od:   {_fmt(w.valid_from)}")
        print(f"  Ważność do:   {_fmt(w.valid_to)}")
        print(f"  Treść:        {w.content}")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())

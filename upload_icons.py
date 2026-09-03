#!/usr/bin/env python3
"""Ręczne wgranie ikon pogodowych na AWTRIX - odpowiednik oryginalnego
`upload_icon.sh` z repo jeeftor, ale bez interakcji: bierze listę ikon i
urządzeń wprost z Twojego config.yaml.

Użycie:
    python upload_icons.py -c config.yaml              # wgraj tylko brakujące
    python upload_icons.py -c config.yaml --all         # wgraj/nadpisz wszystkie
    python upload_icons.py -c config.yaml --device 192.168.1.51  # tylko to urządzenie
"""
from __future__ import annotations

import argparse
import logging
import sys

from awtrix_weather.config import load_config
from awtrix_weather.icon_check import fetch_device_icon_names
from awtrix_weather.icon_upload import download_icon_gif, upload_icon_to_device


def main() -> int:
    parser = argparse.ArgumentParser(description="Wgraj ikony pogodowe na AWTRIX (transport HTTP)")
    parser.add_argument("-c", "--config", default="config.yaml")
    parser.add_argument("--device", help="Ogranicz do jednego urządzenia (IP)")
    parser.add_argument("--all", action="store_true", help="Wgraj/nadpisz wszystkie ikony, nie tylko brakujące")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)-8s %(message)s",
    )
    log = logging.getLogger("upload_icons")

    cfg = load_config(args.config)

    if cfg.awtrix.transport != "http":
        log.error("Ten skrypt działa tylko dla awtrix.transport: http (masz: %s)", cfg.awtrix.transport)
        return 1

    devices = [args.device] if args.device else cfg.awtrix.devices
    if not devices:
        log.error("Brak urządzeń w konfiguracji (awtrix.devices)")
        return 1

    icon_names = sorted({icon for icon in cfg.weather.icons.values() if icon and not str(icon).isdigit()})
    if not icon_names:
        log.error("Brak ikon w konfiguracji (weather.icons)")
        return 1

    scheme = "https" if cfg.awtrix.http.use_https else "http"
    timeout = cfg.awtrix.http.timeout

    exit_code = 0
    for device in devices:
        base_url = f"{scheme}://{device}:{cfg.awtrix.http.port}"

        to_upload = icon_names
        if not args.all:
            available = fetch_device_icon_names(base_url, timeout)
            if available is None:
                log.warning(
                    "%s: nie udało się pobrać listy istniejących ikon - wgrywam wszystkie "
                    "(użyj --all żeby to zrobić świadomie i bez tego ostrzeżenia)",
                    device,
                )
            else:
                to_upload = [name for name in icon_names if name not in available]
                if not to_upload:
                    log.info("%s: wszystkie ikony już wgrane, nic do zrobienia.", device)
                    continue

        log.info("%s: wgrywam %d ikon...", device, len(to_upload))
        for icon_name in to_upload:
            gif_bytes = download_icon_gif(icon_name, timeout)
            if gif_bytes is None:
                log.error(
                    "%s: ikony '%s' nie ma w zestawie jeeftor/HomeAssistant - wgraj ją ręcznie przez web UI.",
                    device,
                    icon_name,
                )
                exit_code = 1
                continue
            if upload_icon_to_device(base_url, icon_name, gif_bytes, timeout):
                log.info("%s: OK - %s", device, icon_name)
            else:
                exit_code = 1

    return exit_code


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
import os
import sys

from awtrix_weather.app import run
from awtrix_weather.config import load_config


def main() -> int:
    parser = argparse.ArgumentParser(description="AWTRIX Weather + Forecast + Moon (standalone)")
    parser.add_argument(
        "-c", "--config", default=os.environ.get("CONFIG_PATH", "config.yaml"),
        help="Ścieżka do pliku konfiguracyjnego YAML (domyślnie config.yaml)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Logowanie na poziomie DEBUG"
    )
    args = parser.parse_args()

    verbose = args.verbose or os.environ.get("LOG_LEVEL", "").upper() == "DEBUG"
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )

    cfg = load_config(args.config)
    run(cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())

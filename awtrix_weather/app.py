from __future__ import annotations

import logging
import time

from .awtrix_client import create_client
from .config import AppConfig
from .icon_check import validate_icons
from .icon_upload import sync_missing_icons
from .metar import CachingMetarReader, build_wx_payload
from .pressure import PressureTrendTracker, build_pressure_payload
from .render import build_payloads
from .sanity_check import check_color_matrix_units
from .weather import create_provider
from .weather.caching import CachingWeatherProvider

log = logging.getLogger(__name__)


def run(cfg: AppConfig) -> None:
    check_color_matrix_units(cfg)

    provider = CachingWeatherProvider(
        create_provider(cfg.weather.provider, openweathermap_api_key=cfg.weather.openweathermap_api_key),
        cfg.weather.refresh_seconds,
    )
    client = create_client(cfg.awtrix)
    client.connect()

    pressure_tracker = PressureTrendTracker(cfg.pressure.trend_window_hours) if cfg.pressure.enabled else None

    metar_reader = None
    if cfg.weather.metar_override.enabled:
        metar_reader = CachingMetarReader(
            cfg.weather.metar_override.station,
            cfg.weather.metar_override.avwx_api_key,
            cfg.weather.metar_override.refresh_seconds,
        )

    try:
        if cfg.awtrix.check_icons_on_start:
            missing = validate_icons(cfg)
            if missing and cfg.awtrix.auto_upload_missing_icons:
                sync_missing_icons(cfg, missing)
    except Exception:
        log.exception("Walidacja/upload ikon nie powiódł się (pomijam, to tylko diagnostyka)")

    log.info(
        "Start. Dostawca pogody=%s | transport=%s | urządzenia=%s | app_topic=%s | co %ss",
        cfg.weather.provider,
        cfg.awtrix.transport,
        cfg.awtrix.devices,
        cfg.awtrix.app_topic,
        cfg.poll_interval_seconds,
    )

    try:
        while True:
            cycle_start = time.monotonic()
            try:
                main_payload, sun_payload, pressure_hpa, metar_wx_description = build_payloads(
                    provider, cfg, metar_reader
                )

                for device in cfg.awtrix.devices:
                    try:
                        client.send(device, cfg.awtrix.app_topic, main_payload)
                        # Wysyłamy ZAWSZE, nawet pusty payload ({}) - to jedyny sposób,
                        # żeby AWTRIX skasował/wyczyścił appkę, gdy jesteśmy poza oknem
                        # event_minute_threshold (inaczej zostaje ostatni komunikat na
                        # zawsze, np. "zachód słońca" widoczny długo po zachodzie).
                        client.send(device, f"{cfg.awtrix.app_topic}_sun", sun_payload)

                        if cfg.weather.metar_override.enabled and cfg.weather.metar_override.show_wx_alert:
                            wx_payload = build_wx_payload(
                                metar_wx_description, cfg.weather.metar_override.wx_message_duration
                            )
                            # tak samo jak _sun - zawsze wysyłamy, {} czyści appkę gdy
                            # zjawisko ustąpiło (np. przelotny deszcz się skończył)
                            client.send(device, cfg.weather.metar_override.wx_app_topic, wx_payload)
                    except Exception:
                        log.error("Nie udało się wysłać do %s (pomijam to urządzenie w tym cyklu)", device, exc_info=True)

                if pressure_tracker is not None:
                    if pressure_hpa is not None:
                        pressure_tracker.record(pressure_hpa)
                        trend = pressure_tracker.trend()
                        pressure_payload = build_pressure_payload(pressure_hpa, trend, cfg.pressure)
                        for device in cfg.awtrix.devices:
                            try:
                                client.send(device, cfg.pressure.app_topic, pressure_payload)
                            except Exception:
                                log.error("Nie udało się wysłać ciśnienia do %s", device, exc_info=True)
                        log.debug("Ciśnienie: %.1f hPa, trend=%s", pressure_hpa, trend)
                    else:
                        log.warning(
                            "pressure.enabled=true, ale dostawca pogody %s nie zwrócił ciśnienia",
                            cfg.weather.provider,
                        )

                log.info(
                    "Zaktualizowano %s urządzeń (weather=%s)",
                    len(cfg.awtrix.devices),
                    main_payload.get("weather"),
                )
            except Exception:
                log.exception(
                    "Błąd podczas przygotowania danych (pogoda/astronomia) - próbuję ponownie za %ss",
                    cfg.poll_interval_seconds,
                )

            elapsed = time.monotonic() - cycle_start
            sleep_for = max(1.0, cfg.poll_interval_seconds - elapsed)
            time.sleep(sleep_for)
    except KeyboardInterrupt:
        log.info("Zatrzymano (Ctrl+C)")
    finally:
        client.disconnect()

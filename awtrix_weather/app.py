from __future__ import annotations

import logging
import time

from .awtrix_client import AwtrixUnreachableError, create_client
from .config import AppConfig
from .icon_check import validate_icons
from .icon_upload import sync_missing_icons
from .imgw_warnings import CachingImgwWarningsReader, build_alert_payload
from .metar import CachingMetarReader, build_wx_payload
from .pressure import PressureTrendTracker, build_pressure_payload
from .render import build_payloads
from .sanity_check import check_color_matrix_units, check_teryt_code
from .weather import create_provider
from .weather.caching import CachingWeatherProvider

log = logging.getLogger(__name__)


def _send(client, device: str, app_name: str, payload: dict, unreachable: set[str]) -> None:
    """Wysyła jeden payload do jednego urządzenia, z ładną obsługą błędów:

    - jeśli urządzenie już okazało się nieosiągalne w tym cyklu (jest w
      `unreachable`), w ogóle nie próbujemy ponownie - jedno urządzenie offline
      nie ma sensu bombardować 3-4 razy w tej samej sekundzie (appka pogody,
      wschód/zachód, ciśnienie, ostrzeżenia - każda osobno by próbowała),
    - `AwtrixUnreachableError` (offline, timeout, zły IP) loguje się jako
      JEDNA czytelna linijka, bez pełnego tracebacka requests/urllib3,
    - każdy inny, nieoczekiwany wyjątek nadal loguje się z pełnym
      tracebackiem (`exc_info=True`) - to może być prawdziwy bug, nie warto
      go wyciszać.
    """
    if device in unreachable:
        log.debug("%s: pomijam wysyłkę do %s (już nieosiągalne w tym cyklu)", app_name, device)
        return
    try:
        client.send(device, app_name, payload)
    except AwtrixUnreachableError as exc:
        log.error("%s nieosiągalne (%s) - pomijam do końca tego cyklu", exc.device, exc.reason)
        unreachable.add(device)
    except Exception:
        log.error("Nie udało się wysłać '%s' do %s", app_name, device, exc_info=True)


def run(cfg: AppConfig) -> None:
    check_color_matrix_units(cfg)
    check_teryt_code(cfg)

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

    warnings_reader = None
    if cfg.imgw_warnings.enabled:
        warnings_reader = CachingImgwWarningsReader(
            cfg.imgw_warnings.teryt, cfg.imgw_warnings.refresh_seconds
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
            unreachable: set[str] = set()
            try:
                main_payload, sun_payload, pressure_hpa, metar_wx_description, current_condition = build_payloads(
                    provider, cfg, metar_reader
                )

                for device in cfg.awtrix.devices:
                    _send(client, device, cfg.awtrix.app_topic, main_payload, unreachable)
                    # Wysyłamy ZAWSZE, nawet pusty payload ({}) - AwtrixClient.send()
                    # zamienia to na skasowanie appki (HTTP: DELETE .../apps/<app>,
                    # MQTT: pusty payload na tym samym topicu - patrz awtrix_client.py),
                    # gdy jesteśmy poza oknem event_minute_threshold (inaczej zostaje
                    # ostatni komunikat na zawsze, np. "zachód słońca" widoczny długo
                    # po zachodzie).
                    _send(client, device, f"{cfg.awtrix.app_topic}_sun", sun_payload, unreachable)

                    if cfg.weather.metar_override.enabled and cfg.weather.metar_override.show_wx_alert:
                        wx_payload = build_wx_payload(
                            metar_wx_description, cfg.weather.metar_override.wx_message_duration
                        )
                        _send(client, device, cfg.weather.metar_override.wx_app_topic, wx_payload, unreachable)

                if pressure_tracker is not None:
                    if pressure_hpa is not None:
                        pressure_tracker.record(pressure_hpa)
                        trend = pressure_tracker.trend()
                        pressure_payload = build_pressure_payload(pressure_hpa, trend, cfg.pressure)
                        for device in cfg.awtrix.devices:
                            _send(client, device, cfg.pressure.app_topic, pressure_payload, unreachable)
                        log.debug("Ciśnienie: %.1f hPa, trend=%s", pressure_hpa, trend)
                    else:
                        log.warning(
                            "pressure.enabled=true, ale dostawca pogody %s nie zwrócił ciśnienia",
                            cfg.weather.provider,
                        )

                if warnings_reader is not None:
                    try:
                        warnings = warnings_reader.read()
                        alert_payload = build_alert_payload(warnings, cfg.imgw_warnings.message_duration)
                        for device in cfg.awtrix.devices:
                            _send(client, device, cfg.imgw_warnings.app_topic, alert_payload, unreachable)
                    except Exception:
                        log.warning(
                            "Nie udało się pobrać ostrzeżeń IMGW dla %s - pomijam ten cykl",
                            cfg.imgw_warnings.teryt,
                            exc_info=True,
                        )

                ok_count = len(cfg.awtrix.devices) - len(unreachable)
                log.info(
                    "Zaktualizowano %s/%s urządzeń (weather=%s)%s",
                    ok_count,
                    len(cfg.awtrix.devices),
                    current_condition,
                    f" - nieosiągalne: {', '.join(sorted(unreachable))}" if unreachable else "",
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

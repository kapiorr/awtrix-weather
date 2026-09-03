"""Sprawdzenie na starcie, czy skonfigurowane ikony (`weather.icons`) faktycznie
są wgrane na AWTRIX-ie, żeby zamiast animowanej ikony nie wyskoczył pusty kwadrat.

Działa tylko dla transportu `http` (mamy wtedy adres IP urządzenia). AWTRIX3
udostępnia listing plików pod tym samym adresem co wbudowany file manager
(http://<ip>/edit -> GET /edit?list=/ICONS), więc z tego korzystamy.

To jest "best effort": format odpowiedzi nie jest formalnie udokumentowany w
API AWTRIX3, więc jeśli parsowanie się nie powiedzie albo endpoint nie
odpowie tak jak oczekujemy, tylko logujemy ostrzeżenie i NIE przerywamy
startu aplikacji - sama wysyłka pogody działa niezależnie od tej walidacji.

Ikony podane jako liczby (np. wbudowane ID LaMetric używane przy podmianie
ikony `clear-night` na fazę księżyca) są pomijane - AWTRIX potrafi je pobrać
sam na żądanie i nie leżą w /ICONS jako pliki, dopóki nie zostaną pobrane.
"""
from __future__ import annotations

import logging

import requests

from .config import AppConfig

log = logging.getLogger(__name__)


def _icon_basename(raw_name: str) -> str:
    name = raw_name.rsplit("/", 1)[-1]
    if "." in name:
        name = name.rsplit(".", 1)[0]
    return name


def _try_list_endpoint(url: str, timeout: float) -> list | None:
    try:
        resp = requests.get(url, timeout=timeout)
    except Exception as exc:
        log.debug("Błąd zapytania %s: %s", url, exc)
        return None
    if resp.status_code != 200:
        log.debug("%s -> HTTP %s", url, resp.status_code)
        return None
    try:
        data = resp.json()
    except ValueError:
        log.debug(
            "%s nie zwrócił JSON (Content-Type=%s), pierwsze 120 znaków: %r",
            url, resp.headers.get("Content-Type"), resp.text[:120],
        )
        return None
    if not isinstance(data, list):
        log.debug("%s zwrócił JSON, ale nie listę: %r", url, type(data))
        return None
    return data


def fetch_device_icon_names(base_url: str, timeout: float) -> set[str] | None:
    """Zwraca zbiór nazw ikon (bez rozszerzenia) wgranych na urządzeniu,
    albo None jeśli nie udało się tego ustalić (np. inna wersja firmware).

    Format listingu plików nie jest formalnie udokumentowany w API AWTRIX3,
    więc próbujemy po kolei kilka wariantów spotykanych w firmware opartych
    na ESPAsyncWebServer. WAŻNE: ukośnik w wartości `dir=`/`list=` musi
    zostać w URL dosłownie jako "/", NIE zakodowany jako "%2F" - część
    firmware'ów AWTRIX-a nie dekoduje go z powrotem i wtedy dostajemy zwykłą
    stronę HTML zamiast JSON. Dlatego budujemy URL ręcznie, bez `params=`."""
    attempts = [
        f"{base_url}/list?dir=/ICONS",
        f"{base_url}/edit?list=/ICONS",
    ]

    data = None
    for url in attempts:
        data = _try_list_endpoint(url, timeout)
        if data is not None:
            break

    if data is None:
        return None

    names: set[str] = set()
    for entry in data:
        if isinstance(entry, str):
            names.add(_icon_basename(entry))
        elif isinstance(entry, dict):
            raw = entry.get("name") or entry.get("path") or entry.get("file")
            if isinstance(raw, str):
                names.add(_icon_basename(raw))
    return names


def validate_icons(cfg: AppConfig) -> dict[str, list[str]]:
    """Zwraca {device: [brakujące_nazwy_ikon, ...]} (tylko dla transport=http)."""
    missing_by_device: dict[str, list[str]] = {}

    if cfg.awtrix.transport != "http":
        log.info(
            "Walidacja ikon dostępna tylko dla transport=http (dla mqtt sprawdź ręcznie w web UI AWTRIX-a)."
        )
        return missing_by_device

    expected = {
        name: icon
        for name, icon in cfg.weather.icons.items()
        if icon and not str(icon).isdigit()
    }
    if not expected:
        return missing_by_device

    scheme = "https" if cfg.awtrix.http.use_https else "http"

    for device in cfg.awtrix.devices:
        base_url = f"{scheme}://{device}:{cfg.awtrix.http.port}"
        available = fetch_device_icon_names(base_url, cfg.awtrix.http.timeout)
        if available is None:
            log.warning(
                "%s: nie udało się zweryfikować wgranych ikon (żaden ze znanych endpointów "
                "listingu plików nie zadziałał - uruchom z -v/LOG_LEVEL=DEBUG, żeby zobaczyć "
                "surowe odpowiedzi urządzenia) - sprawdź ręcznie w web UI urządzenia.",
                device,
            )
            continue

        missing = sorted(
            {icon for condition, icon in expected.items() if icon not in available}
        )
        if missing:
            missing_by_device[device] = missing
            log.warning(
                "%s: brakuje %d ikon na urządzeniu (folder /ICONS): %s.",
                device,
                len(missing),
                ", ".join(missing),
            )
        else:
            log.info("%s: wszystkie skonfigurowane ikony są wgrane.", device)

    return missing_by_device

"""Sprawdzenie na starcie, czy skonfigurowane ikony (`weather.icons`) faktycznie
są wgrane na AWTRIX-ie, żeby zamiast animowanej ikony nie wyskoczył pusty kwadrat.

Działa tylko dla transportu `http` (mamy wtedy adres IP urządzenia). W
odróżnieniu od AWTRIX 3 (gdzie listing plików nie był formalnie
udokumentowany i trzeba było zgadywać endpoint), AWTRIX NG ma to w oficjalnym
API v1:

    GET /api/v1/files?dir=/ICONS
    -> {"files": [{"name": "w-sunny.gif", "size": 1234}, ...],
        "usedBytes": ..., "totalBytes": ...}

(patrz https://blueforcer.github.io/awtrix-ng/guides/icons/#list-and-delete
oraz https://blueforcer.github.io/awtrix-ng/reference/http/#files). Listing
katalogu, który jeszcze nie istnieje, zwraca 200 z pustą listą `files`, nie
404 - traktujemy to więc po prostu jako "zero ikon wgranych".

To nadal jest "best effort": jeśli zapytanie się nie powiedzie z innego
powodu (urządzenie offline, stary firmware itp.), tylko logujemy ostrzeżenie
i NIE przerywamy startu aplikacji - sama wysyłka pogody działa niezależnie
od tej walidacji.

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


def fetch_device_icon_names(base_url: str, timeout: float) -> set[str] | None:
    """Zwraca zbiór nazw ikon (bez rozszerzenia) wgranych na urządzeniu w
    /ICONS, albo None jeśli zapytanie się nie powiodło (urządzenie
    nieosiągalne, nieoczekiwana odpowiedź...)."""
    url = f"{base_url}/api/v1/files"
    try:
        resp = requests.get(url, params={"dir": "/ICONS"}, timeout=timeout)
    except requests.RequestException as exc:
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

    files = data.get("files") if isinstance(data, dict) else None
    if not isinstance(files, list):
        log.debug("%s zwrócił nieoczekiwany kształt JSON (brak listy 'files'): %r", url, data)
        return None

    names: set[str] = set()
    for entry in files:
        if isinstance(entry, dict):
            raw = entry.get("name")
            if isinstance(raw, str):
                names.add(_icon_basename(raw))
        elif isinstance(entry, str):
            names.add(_icon_basename(entry))
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
                "%s: nie udało się zweryfikować wgranych ikon (GET /api/v1/files nie "
                "odpowiedział jak oczekiwano - uruchom z -v/LOG_LEVEL=DEBUG, żeby "
                "zobaczyć surową odpowiedź urządzenia) - sprawdź ręcznie w web UI urządzenia.",
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

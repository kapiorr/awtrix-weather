"""Pobiera brakujące ikony pogodowe wprost z repo jeeftor/HomeAssistant
(ten sam zestaw, który pobierał oryginalny `upload_icon.sh`) i wgrywa je na
AWTRIX NG przez API v1 plików.

Format uploadu (AWTRIX NG, patrz
https://blueforcer.github.io/awtrix-ng/guides/icons/#upload-an-icon):

    POST /api/v1/files?dir=/ICONS
    multipart/form-data, dowolna nazwa pola - liczy się tylko nazwa pliku.

Nazwa pliku (bez rozszerzenia) staje się ID ikony używanym w payloadzie
(`"icon": "<id>"`). AWTRIX NG akceptuje GIF i JPEG w /ICONS - używamy GIF-a,
tak jak oryginalny zestaw jeeftora.
"""
from __future__ import annotations

import logging

import requests

from .config import AppConfig

log = logging.getLogger(__name__)

ICON_SOURCE_BASE = "https://raw.githubusercontent.com/jeeftor/HomeAssistant/master/icons/weather"


def download_icon_gif(icon_name: str, timeout: float = 10.0) -> bytes | None:
    """Pobiera <icon_name>.gif z repo jeeftor. None jeśli nie istnieje tam
    (np. własna, niestandardowa nazwa ikony) albo coś poszło nie tak."""
    url = f"{ICON_SOURCE_BASE}/{icon_name}.gif"
    try:
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        content = resp.content
        if not content.startswith(b"GIF8"):
            log.warning("%s nie wygląda na poprawny GIF - pomijam upload", url)
            return None
        return content
    except requests.RequestException as exc:
        log.warning("Nie udało się pobrać %s: %s", url, exc)
        return None


def upload_icon_to_device(
    base_url: str, icon_name: str, gif_bytes: bytes, timeout: float = 10.0
) -> bool:
    """Wgrywa ikonę pod `/ICONS/<icon_name>.gif` przez API v1 AWTRIX NG.

    Nazwa pola formularza jest dowolna - liczy się wyłącznie nazwa pliku
    w multipart, bo to ona staje się nazwą (a więc i ID) ikony na urządzeniu."""
    try:
        resp = requests.post(
            f"{base_url}/api/v1/files",
            params={"dir": "/ICONS"},
            files={"file": (f"{icon_name}.gif", gif_bytes, "image/gif")},
            timeout=timeout,
        )
        resp.raise_for_status()
        return True
    except requests.RequestException as exc:
        log.warning("Upload %s na %s nie powiódł się: %s", icon_name, base_url, exc)
        return False


def sync_missing_icons(cfg: AppConfig, missing_by_device: dict[str, list[str]]) -> None:
    """missing_by_device: {"192.168.1.50": ["w-sunny", "w-rainy", ...], ...}
    (nazwy ikon bez rozszerzenia, tak jak w weather.icons)."""
    if not missing_by_device:
        return

    scheme = "https" if cfg.awtrix.http.use_https else "http"
    timeout = cfg.awtrix.http.timeout

    # Cache pobranych GIF-ów - jedna ikona pobierana raz, nawet gdy brakuje
    # jej na kilku urządzeniach.
    downloaded: dict[str, bytes | None] = {}

    for device, icon_names in missing_by_device.items():
        base_url = f"{scheme}://{device}:{cfg.awtrix.http.port}"
        for icon_name in icon_names:
            if icon_name not in downloaded:
                downloaded[icon_name] = download_icon_gif(icon_name, timeout)
            gif_bytes = downloaded[icon_name]

            if gif_bytes is None:
                log.warning(
                    "%s: brak ikony '%s' w zestawie jeeftor/HomeAssistant - wgraj ją ręcznie.",
                    device,
                    icon_name,
                )
                continue

            if upload_icon_to_device(base_url, icon_name, gif_bytes, timeout):
                log.info("%s: wgrano brakującą ikonę '%s'.", device, icon_name)

"""Wysyłka payloadu do AWTRIX NG - dwa warianty transportu:

- http: bezpośrednio na lokalne API v1 urządzenia (bez brokera MQTT):
    utworzenie/aktualizacja appki:  PUT  http://<ip>/api/v1/apps/pushed/<app>
    usunięcie appki:                DELETE http://<ip>/api/v1/apps/<app>
  (AWTRIX NG, w odróżnieniu od AWTRIX 3, NIE kasuje appki pustym/`{}` body
  wysłanym na PUT przez HTTP - to teraz osobny endpoint DELETE, patrz
  https://blueforcer.github.io/awtrix-ng/reference/payload/#pushed-apps).
- mqtt: publikacja na broker, nowe drzewo tematów AWTRIX NG:
    <device_prefix>/cmd/apps/pushed/<app>
  Na MQTT usuwanie pustym payloadem/`{}` nadal działa tak jak w AWTRIX 3.

`devices` w konfiguracji oznacza co innego w zależności od transportu:
  http -> adresy IP/hostname urządzeń
  mqtt -> bazowe prefiksy MQTT urządzeń (np. "awtrix_abcdef", ustawione w
          System -> MQTT -> Prefix na urządzeniu)
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod

import requests

from .config import AwtrixConfig

log = logging.getLogger(__name__)


class AwtrixUnreachableError(Exception):
    """Urządzenie AWTRIX nieosiągalne (offline, zły IP, brak trasy w sieci,
    timeout...) - odróżniamy to celowo od innych błędów, żeby móc zalogować
    jedną czytelną linijkę zamiast pełnego tracebacka requests/urllib3, i
    żeby nie próbować bombardować tego samego martwego urządzenia w kółko
    w ramach jednego cyklu."""

    def __init__(self, device: str, reason: str):
        self.device = device
        self.reason = reason
        super().__init__(f"{device}: {reason}")


class AwtrixClient(ABC):
    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def send(self, device: str, app_name: str, payload: dict) -> None:
        """Wysyła/aktualizuje appkę `app_name`. Pusty payload ({}) KASUJE
        appkę (na HTTP realizowane jako osobne wywołanie DELETE, na MQTT
        jako publikacja pustego payloadu - patrz moduł docstring)."""
        ...


class HttpAwtrixClient(AwtrixClient):
    def __init__(self, cfg: AwtrixConfig):
        self.cfg = cfg
        self._session = requests.Session()

    def connect(self) -> None:
        pass  # bezstanowe - nic do zrobienia

    def disconnect(self) -> None:
        self._session.close()

    def _base_url(self, device: str) -> str:
        scheme = "https" if self.cfg.http.use_https else "http"
        return f"{scheme}://{device}:{self.cfg.http.port}"

    def send(self, device: str, app_name: str, payload: dict) -> None:
        if not payload:
            self._delete(device, app_name)
            return

        url = f"{self._base_url(device)}/api/v1/apps/pushed/{app_name}"
        try:
            resp = self._session.put(
                url,
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                timeout=self.cfg.http.timeout,
            )
            resp.raise_for_status()
        except requests.exceptions.ConnectionError as exc:
            raise AwtrixUnreachableError(device, "brak połączenia (offline? zły IP? sieć?)") from exc
        except requests.exceptions.Timeout as exc:
            raise AwtrixUnreachableError(device, f"timeout ({self.cfg.http.timeout}s)") from exc
        except requests.exceptions.HTTPError as exc:
            raise AwtrixUnreachableError(
                device, f"HTTP {resp.status_code} ({_error_detail(resp)})"
            ) from exc
        log.debug("PUT -> %s: %s", url, payload)

    def _delete(self, device: str, app_name: str) -> None:
        url = f"{self._base_url(device)}/api/v1/apps/{app_name}"
        try:
            resp = self._session.delete(url, timeout=self.cfg.http.timeout)
            # 404 = appki i tak już nie ma na urządzeniu (np. nigdy nie
            # została wysłana w tym cyklu życia AWTRIX-a) - to nie błąd.
            if resp.status_code not in (200, 404):
                resp.raise_for_status()
        except requests.exceptions.ConnectionError as exc:
            raise AwtrixUnreachableError(device, "brak połączenia (offline? zły IP? sieć?)") from exc
        except requests.exceptions.Timeout as exc:
            raise AwtrixUnreachableError(device, f"timeout ({self.cfg.http.timeout}s)") from exc
        except requests.exceptions.HTTPError as exc:
            raise AwtrixUnreachableError(
                device, f"HTTP {resp.status_code} ({_error_detail(resp)})"
            ) from exc
        log.debug("DELETE -> %s", url)


def _error_detail(resp: requests.Response) -> str:
    """AWTRIX NG odpowiada błędem jako {"error": {"code", "message", "field?"}}
    - wyciągamy to do czytelnego loga zamiast gołego kodu HTTP."""
    try:
        err = resp.json().get("error", {})
        field = f" pole={err['field']}" if err.get("field") else ""
        return f"{err.get('code', '?')}: {err.get('message', '?')}{field}"
    except Exception:
        return resp.text[:200]


class MqttAwtrixClient(AwtrixClient):
    def __init__(self, cfg: AwtrixConfig):
        import paho.mqtt.client as mqtt  # import lokalny - nieużywane przy transport=http

        self.cfg = cfg
        self._mqtt = mqtt
        self.client = mqtt.Client(client_id=cfg.mqtt.client_id, clean_session=True)
        if cfg.mqtt.username:
            self.client.username_pw_set(cfg.mqtt.username, cfg.mqtt.password or None)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            log.info("Połączono z brokerem MQTT %s:%s", self.cfg.mqtt.host, self.cfg.mqtt.port)
        else:
            log.error("Błąd połączenia MQTT, rc=%s", rc)

    def _on_disconnect(self, client, userdata, rc):
        log.warning("Rozłączono z MQTT (rc=%s)", rc)

    def connect(self) -> None:
        self.client.connect(self.cfg.mqtt.host, self.cfg.mqtt.port, keepalive=60)
        self.client.loop_start()

    def disconnect(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()

    def send(self, device: str, app_name: str, payload: dict) -> None:
        # AWTRIX NG: nowe drzewo tematów - custom/<app> -> cmd/apps/pushed/<app>.
        # Pusty payload nadal kasuje appkę (bez zmian względem AWTRIX 3).
        topic = f"{device}/cmd/apps/pushed/{app_name}"
        body = json.dumps(payload, ensure_ascii=False) if payload else ""
        try:
            result = self.client.publish(topic, body, qos=0, retain=False)
            result.wait_for_publish(timeout=5)
        except (RuntimeError, ValueError) as exc:
            raise AwtrixUnreachableError(device, f"publikacja MQTT nie powiodła się ({exc})") from exc
        log.debug("MQTT -> %s: %s", topic, body or "(delete)")


def create_client(cfg: AwtrixConfig) -> AwtrixClient:
    if cfg.transport == "http":
        return HttpAwtrixClient(cfg)
    if cfg.transport == "mqtt":
        return MqttAwtrixClient(cfg)
    raise ValueError(f"Nieznany transport AWTRIX: {cfg.transport!r} (dozwolone: http, mqtt)")

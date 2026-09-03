"""Wysyłka payloadu do AWTRIX - dwa warianty transportu:

- http: bezpośrednio POST na lokalne API urządzenia (bez brokera MQTT):
  POST http://<ip>:<port>/api/custom?name=<app>   (Blueforcer AWTRIX3 HTTP API)
- mqtt: publikacja na broker, tak jak w oryginalnym blueprincie HA:
  <device_topic>/custom/<app>

`devices` w konfiguracji oznacza co innego w zależności od transportu:
  http -> adresy IP/hostname urządzeń
  mqtt -> bazowe topiki MQTT urządzeń (np. "awtrix_abcdef")
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod

import requests

from .config import AwtrixConfig

log = logging.getLogger(__name__)


class AwtrixClient(ABC):
    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def send(self, device: str, app_name: str, payload: dict) -> None: ...


class HttpAwtrixClient(AwtrixClient):
    def __init__(self, cfg: AwtrixConfig):
        self.cfg = cfg
        self._session = requests.Session()

    def connect(self) -> None:
        pass  # bezstanowe - nic do zrobienia

    def disconnect(self) -> None:
        self._session.close()

    def send(self, device: str, app_name: str, payload: dict) -> None:
        scheme = "https" if self.cfg.http.use_https else "http"
        url = f"{scheme}://{device}:{self.cfg.http.port}/api/custom"
        resp = self._session.post(
            url,
            params={"name": app_name},
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            timeout=self.cfg.http.timeout,
        )
        resp.raise_for_status()
        log.debug("HTTP -> %s (%s): %s", url, app_name, payload)


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
        topic = f"{device}/custom/{app_name}"
        body = json.dumps(payload, ensure_ascii=False)
        result = self.client.publish(topic, body, qos=0, retain=False)
        result.wait_for_publish(timeout=5)
        log.debug("MQTT -> %s: %s", topic, body)


def create_client(cfg: AwtrixConfig) -> AwtrixClient:
    if cfg.transport == "http":
        return HttpAwtrixClient(cfg)
    if cfg.transport == "mqtt":
        return MqttAwtrixClient(cfg)
    raise ValueError(f"Nieznany transport AWTRIX: {cfg.transport!r} (dozwolone: http, mqtt)")

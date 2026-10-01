"""Lekki serwer HTTP (stdlib, bez nowej zależności) wystawiający ostatnio
pobrane dane (pogoda/METAR/ostrzeżenia IMGW/trend ciśnienia) jako JSON.

To NIE jest endpoint, który sam odpytuje dostawców przy każdym żądaniu -
serwuje wyłącznie to, co już jest w pamięci, zaktualizowane przez główną
pętlę (`app.py`) dokładnie wtedy, kiedy ta faktycznie pobierze świeże dane
(czyli zgodnie z `weather.refresh_seconds` / `metar_override.refresh_seconds`
/ `imgw_warnings.refresh_seconds` - każda sekcja ma swój wlasny znacznik
czasu `updated_at`, bo odświeżają się w różnym tempie). Dzięki temu odpytanie
tego API jest "darmowe" - nie bije dodatkowo w zewnętrzne serwisy pogodowe,
nawet jeśli ktoś odpytuje je co sekundę.
"""
from __future__ import annotations

import dataclasses
import json
import logging
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .config import HttpApiConfig

log = logging.getLogger(__name__)


def _json_default(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    raise TypeError(f"Nie umiem zserializować {type(obj)!r} do JSON")


class StateStore:
    """Wątkowo-bezpieczny magazyn na ostatnio pobrane dane. Każda sekcja
    (`weather`, `metar`, `imgw`, `pressure`) ma własny `updated_at` - przy
    chwilowym błędzie pobierania JEDNEJ sekcji (np. METAR padnie, pogoda
    nadal działa), reszta endpointu nie gaśnie - ta jedna sekcja po prostu
    pokazuje coraz starszy `updated_at`, zamiast znikać."""

    def __init__(self):
        self._lock = threading.Lock()
        self._data: dict = {}

    def _set(self, key: str, value: dict) -> None:
        value = dict(value)
        value["updated_at"] = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._data[key] = value

    def update_weather(self, weather_data, condition: str) -> None:
        self._set(
            "weather",
            {
                "condition": condition,
                "current": weather_data.current,
                "hourly": weather_data.hourly,
            },
        )

    def update_moon(self, moon_info: dict) -> None:
        self._set("moon", dict(moon_info))

    def update_metar(self, reading) -> None:
        self._set("metar", {"reading": reading})

    def update_imgw(self, teryt: str, all_warnings: list, active: list) -> None:
        self._set(
            "imgw",
            {"teryt": teryt, "active": active, "all_for_teryt": all_warnings},
        )

    def update_pressure(self, hpa: float, trend: str | None) -> None:
        self._set("pressure", {"hpa": hpa, "trend": trend})

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._data)


class _Handler(BaseHTTPRequestHandler):
    state: StateStore  # ustawiane dynamicznie przy tworzeniu klasy w start()

    def do_GET(self):
        body = json.dumps(self.state.snapshot(), default=_json_default, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - sygnatura z BaseHTTPRequestHandler
        # Domyślnie leciałoby to na stderr przy KAŻDYM żądaniu - przepinamy
        # na nasz logger (DEBUG, żeby nie zaśmiecać normalnych logów).
        log.debug("http_api: %s - %s", self.address_string(), format % args)


def start(cfg: HttpApiConfig, state: StateStore) -> ThreadingHTTPServer:
    """Startuje serwer w wątku-demonie (kończy się razem z procesem, nie
    trzeba go osobno ubijać na SIGKILL) i zwraca instancję serwera, żeby
    `app.py` mógł go porządnie zamknąć w `finally` (`server.shutdown()`)."""
    handler_cls = type("StateHandler", (_Handler,), {"state": state})
    server = ThreadingHTTPServer((cfg.host, cfg.port), handler_cls)
    thread = threading.Thread(target=server.serve_forever, name="http-api", daemon=True)
    thread.start()
    log.info("HTTP API ze stanem pogody wystawione na http://%s:%s/", cfg.host, cfg.port)
    return server

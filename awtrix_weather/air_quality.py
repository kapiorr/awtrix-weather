"""Jakość powietrza z miejskiego API Urzędu m.st. Warszawy
(dane.um.warszawa.pl - "Monitoring jakości powietrza"). Wymaga tokenu API
(darmowa rejestracja na portalu). Endpoint zwraca WSZYSTKIE stacje naraz -
filtrujemy po naszej stronie do kilku wybranych, po polu "name" (np.
"Warszawa-Grochowska") - ten sam wzorzec co IMGW (cały kraj -> jeden powiat),
tylko tu zamiast jednej wybieramy kilka i uśredniamy.

WYŁĄCZNIE do API (http_api.py) - nie ma tu (na razie) odpowiednika appki
AWTRIX jak przy pogodzie/ciśnieniu/IMGW.

Dwa różne "indeksy" w grze, żeby się nie pomylić:
- "overall_index" / PIJP - polski Indeks Jakości Powietrza (GIOŚ), kategorie
  słowne z samego API UM ("Bardzo dobry".."Bardzo zły", 6 poziomów).
- "aqi" - amerykański US EPA AQI (0-500), liczony PRZEZ NAS z uśrednionych
  stężeń PM10/PM2.5 wg oficjalnych progów EPA. To międzynarodowy standard,
  zupełnie inna skala niż PIJP - stąd osobne pole, nie "to samo co overall".
  UWAGA: prawdziwy EPA AQI liczy się ze średniej 24h, a my (bez trzymania
  własnej historii) liczymy go z BIEŻĄCYCH odczytów stacji - to przybliżenie
  ("chwilowy AQI"), tak jak robi wiele publicznych dashboardów, ale nie jest
  to formalnie zgodne z metodologią EPA.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import requests

log = logging.getLogger(__name__)

AIR_QUALITY_URL = "https://dane.um.warszawa.pl/api/action/get_bopipk_monitoring_jakosci_powietrza"

# Polski Indeks Jakości Powietrza (GIOŚ) - 6 poziomów, w kolejności od
# najlepszego do najgorszego. Używane do uśrednienia "overall_index" (bo to
# w API jest tylko nazwą kategorii, nie liczbą) - mapujemy nazwa -> 1..6,
# uśredniamy, mapujemy z powrotem na najbliższą nazwę.
PIJP_LEVELS = ["Bardzo dobry", "Dobry", "Umiarkowany", "Dostateczny", "Zły", "Bardzo zły"]

# Oficjalne progi US EPA AQI: (stężenie_od, stężenie_do, AQI_od, AQI_do),
# wzór liniowej interpolacji wewnątrz przedziału. Osobne tabele dla PM2.5 i
# PM10 (obie w µg/m3, standardowe publicznie dostępne progi EPA).
#
# PM2.5: tabela wg rewizji EPA z 7.02.2024 (weszła w życie 6.05.2024, wraz
# z obniżeniem rocznej normy PM2.5 z 12.0 do 9.0 µg/m3) - NIE stare progi
# sprzed 2024. Zmieniły się granice 50/200/300/500 (dolny próg "Dobry" z
# 12.0 na 9.0, a kategorie Unhealthy/Very Unhealthy/Hazardous ścieśnione +
# dwa dawne przedziały Hazardous (301-400, 401-500) scalone w jeden
# 301-500). Próg 100 (35.4) zostaje bez zmian - EPA utrzymała dobową normę
# PM2.5 na poziomie 35 µg/m3. Źródło: EPA "2024 AQI for Fine Particle
# Pollution" fact sheet (epa.gov/system/files/documents/2024-02/
# pm-naaqs-air-quality-index-fact-sheet.pdf).
# PM10 NIE zostało zrewidowane w 2024 (dobowa norma PM10 zostaje 150 µg/m3),
# więc tabela PM10 niżej to wciąż te same, od dawna obowiązujące progi.
PM25_BREAKPOINTS = [
    (0.0, 9.0, 0, 50),
    (9.1, 35.4, 51, 100),
    (35.5, 55.4, 101, 150),
    (55.5, 125.4, 151, 200),
    (125.5, 225.4, 201, 300),
    (225.5, 325.4, 301, 500),
]
PM10_BREAKPOINTS = [
    (0, 54, 0, 50),
    (55, 154, 51, 100),
    (155, 254, 101, 150),
    (255, 354, 151, 200),
    (355, 424, 201, 300),
    (425, 504, 301, 400),
    (505, 604, 401, 500),
]


@dataclass
class PollutantReading:
    param_code: str      # np. "PM10", "PM25", "NO2", "CO"
    param_name: str      # np. "pył zawieszony PM10"
    value: float | None
    unit: str             # np. "µg/m3"
    time: str             # jak przychodzi z API, np. "2026-07-30 05:00:00" (bez strefy!)
    index_name: str | None  # kategoria PIJP dla TEGO zanieczyszczenia (np. "Dobry")


@dataclass
class AirQualityReading:
    station_name: str
    overall_index: str | None             # zbiorczy PIJP dla tej stacji, np. "Bardzo dobry"
    overall_recommendations: str | None
    lat: float | None
    lon: float | None
    measurements: list[PollutantReading]


@dataclass
class AggregatedAirQuality:
    station_names: list[str] = field(default_factory=list)
    stations_missing: list[str] = field(default_factory=list)  # ktore z configu nie znaleziono
    pm10_avg: float | None = None
    pm25_avg: float | None = None
    overall_avg_level: float | None = None    # 1.0-6.0, srednia numeryczna PIJP
    overall_avg_category: str | None = None   # najblizsza nazwa kategorii dla powyzszego
    aqi_pm10: int | None = None                # czastkowy US EPA AQI liczony tylko z pm10_avg
    aqi_pm25: int | None = None                # czastkowy US EPA AQI liczony tylko z pm25_avg
    aqi: int | None = None                     # finalny = max(aqi_pm10, aqi_pm25)
    aqi_dominant_pollutant: str | None = None  # "PM2.5" albo "PM10" - ktory zdecydowal o aqi


def _fetch_all_stations(token: str, timeout: float = 10.0) -> list[dict]:
    resp = requests.post(AIR_QUALITY_URL, headers={"Authorization": token}, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _parse_station(st: dict, fallback_name: str) -> AirQualityReading:
    ijp = st.get("ijp") or {}
    measurements = []
    for d in st.get("data", []):
        d_ijp = d.get("ijp") or {}
        raw_value = d.get("value")
        try:
            value = float(raw_value) if raw_value is not None else None
        except (TypeError, ValueError):
            value = None
        measurements.append(
            PollutantReading(
                param_code=d.get("param_code", ""),
                param_name=d.get("param_name", ""),
                value=value,
                unit=d.get("unit", ""),
                time=d.get("time", ""),
                index_name=d_ijp.get("name"),
            )
        )
    lat = st.get("lat")
    lon = st.get("lon")
    return AirQualityReading(
        station_name=st.get("name", fallback_name),
        overall_index=ijp.get("name"),
        overall_recommendations=ijp.get("recommendations"),
        lat=float(lat) if lat is not None else None,
        lon=float(lon) if lon is not None else None,
        measurements=measurements,
    )


def fetch_air_quality(token: str, station_name: str, timeout: float = 10.0) -> AirQualityReading | None:
    """Pojedyncza stacja. None gdy nazwa nie występuje w odpowiedzi."""
    stations = _fetch_all_stations(token, timeout)
    for st in stations:
        if st.get("name") == station_name:
            return _parse_station(st, station_name)
    available = ", ".join(sorted(s.get("name", "?") for s in stations))
    log.warning(
        "Stacja jakości powietrza '%s' nie znaleziona w odpowiedzi UM Warszawa. Dostępne nazwy: %s",
        station_name, available,
    )
    return None


def fetch_air_quality_multi(
    token: str, station_names: list[str], timeout: float = 10.0
) -> tuple[list[AirQualityReading], list[str]]:
    """Kilka stacji z JEDNEGO zapytania (UM i tak zwraca wszystkie naraz, więc
    nie ma sensu odpytywać osobno dla każdej z 3 stacji). Zwraca
    (znalezione_odczyty, nazwy_ktorych_nie_znaleziono)."""
    stations = _fetch_all_stations(token, timeout)
    by_name = {st.get("name"): st for st in stations}

    found: list[AirQualityReading] = []
    missing: list[str] = []
    for name in station_names:
        st = by_name.get(name)
        if st is None:
            missing.append(name)
            continue
        found.append(_parse_station(st, name))

    if missing:
        available = ", ".join(sorted(by_name.keys()))
        log.warning(
            "Nie znaleziono %d/%d skonfigurowanych stacji jakości powietrza: %s. Dostępne nazwy: %s",
            len(missing), len(station_names), ", ".join(missing), available,
        )
    return found, missing


def _aqi_from_breakpoints(conc: float, table: list[tuple]) -> int:
    for c_lo, c_hi, aqi_lo, aqi_hi in table:
        if c_lo <= conc <= c_hi:
            return round((aqi_hi - aqi_lo) / (c_hi - c_lo) * (conc - c_lo) + aqi_lo)
    # poza najwyzszym progiem tabeli EPA (bardzo ekstremalne stezenie) - przytnij do 500
    return 500 if conc > table[-1][1] else 0


def _pijp_to_number(name: str | None) -> int | None:
    if name is None:
        return None
    try:
        return PIJP_LEVELS.index(name) + 1
    except ValueError:
        return None


def _number_to_pijp(n: float) -> str:
    idx = max(0, min(len(PIJP_LEVELS) - 1, round(n) - 1))
    return PIJP_LEVELS[idx]


def average_readings(readings: list[AirQualityReading], missing: list[str] | None = None) -> AggregatedAirQuality:
    # UWAGA: API UM Warszawa jest niespojne w zapisie kodu PM2.5 - w
    # dokumentacji/przykladzie bylo "PM25" (bez kropki), a w realnej
    # odpowiedzi API potrafi przyjsc "PM2.5" (z kropka) - akceptujemy oba
    # warianty, zamiast zgadywac ktory akurat zwroci dana stacja.
    PM25_CODES = {"PM25", "PM2.5"}

    pm10_values = [
        m.value for r in readings for m in r.measurements if m.param_code == "PM10" and m.value is not None
    ]
    pm25_values = [
        m.value for r in readings for m in r.measurements if m.param_code in PM25_CODES and m.value is not None
    ]
    overall_numbers = [n for n in (_pijp_to_number(r.overall_index) for r in readings) if n is not None]

    pm10_avg = sum(pm10_values) / len(pm10_values) if pm10_values else None
    pm25_avg = sum(pm25_values) / len(pm25_values) if pm25_values else None
    overall_avg_level = sum(overall_numbers) / len(overall_numbers) if overall_numbers else None
    overall_avg_category = _number_to_pijp(overall_avg_level) if overall_avg_level is not None else None

    aqi_pm10 = _aqi_from_breakpoints(pm10_avg, PM10_BREAKPOINTS) if pm10_avg is not None else None
    aqi_pm25 = _aqi_from_breakpoints(pm25_avg, PM25_BREAKPOINTS) if pm25_avg is not None else None

    aqi: int | None = None
    dominant: str | None = None
    if aqi_pm25 is not None and (aqi_pm10 is None or aqi_pm25 >= aqi_pm10):
        aqi, dominant = aqi_pm25, "PM2.5"
    elif aqi_pm10 is not None:
        aqi, dominant = aqi_pm10, "PM10"

    return AggregatedAirQuality(
        station_names=[r.station_name for r in readings],
        stations_missing=list(missing or []),
        pm10_avg=pm10_avg,
        pm25_avg=pm25_avg,
        overall_avg_level=overall_avg_level,
        overall_avg_category=overall_avg_category,
        aqi_pm10=aqi_pm10,
        aqi_pm25=aqi_pm25,
        aqi=aqi,
        aqi_dominant_pollutant=dominant,
    )


class CachingAirQualityReader:
    def __init__(self, token: str, station_names: list[str], refresh_seconds: int):
        self.token = token
        self.station_names = station_names
        self.refresh_seconds = max(1, refresh_seconds)
        self._cached: list[AirQualityReading] = []
        self._cached_missing: list[str] = []
        self._cached_at: float = 0.0

    def read(self) -> tuple[list[AirQualityReading], list[str]]:
        now = time.monotonic()
        stale = not self._cached_at or (now - self._cached_at) >= self.refresh_seconds
        if stale:
            found, missing = fetch_air_quality_multi(self.token, self.station_names)
            self._cached_at = now
            if found:
                self._cached = found
                self._cached_missing = missing
                log.info(
                    "Jakość powietrza: %s",
                    ", ".join(f"{r.station_name}={r.overall_index or '?'}" for r in found),
                )
            # found puste (np. wszystkie nazwy zle / chwilowy blad sieci) -
            # zostawiamy poprzedni self._cached, zamiast go czyscic.
        return self._cached, self._cached_missing

    def read_aggregated(self) -> AggregatedAirQuality:
        readings, missing = self.read()
        return average_readings(readings, missing)

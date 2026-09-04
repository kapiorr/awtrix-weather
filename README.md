# AWTRIX Weather (w pełni standalone, bez Home Assistant)

> **Pochodzenie projektu:** to konwersja świetnego blueprintu Home Assistant
> [`awtrix_weatherflow.yaml`](https://github.com/jeeftor/HomeAssistant/blob/master/blueprints/automation/awtrix_weatherflow.yaml)
> autorstwa [**jeeftor**](https://github.com/jeeftor) na samodzielny skrypt
> w Pythonie, bez zależności od Home Assistant. Cała logika wyświetlacza
> (ikony, kolory, bitmapy faz księżyca, warunki pokazywania księżyca/wschodu/
> zachodu) została wiernie przeniesiona z oryginału - **wielkie dzięki
> jeeftorowi** za oryginalny projekt i za darmowy zestaw ikon pogodowych
> (`icons/weather/*.gif`), z którego korzysta ten skrypt.

**Bez Home Assistant.** Dane pogodowe, faza księżyca oraz wschody/zachody słońca
są liczone/pobierane bezpośrednio w skrypcie:

- **pogoda** - Open-Meteo (domyślnie, bez klucza API) albo OpenWeatherMap (wymaga klucza) - wybór w `config.yaml`,
- **księżyc i słońce** - liczone lokalnie biblioteką `ephem` na podstawie Twoich współrzędnych (bez żadnego zewnętrznego API do astronomii),
- **AWTRIX** - domyślnie wysyłka przez **lokalne HTTP API urządzenia** (`POST http://<ip>/api/custom?name=...`), bez brokera MQTT. MQTT wciąż jest dostępny jako opcja (`awtrix.transport: mqtt`), jeśli wolisz go zostawić.

Skrypt w pętli (domyślnie co 60 s):
1. pobiera aktualną pogodę + prognozę godzinową od wybranego dostawcy,
2. liczy fazę/wysokość księżyca oraz najbliższy wschód/zachód słońca (`ephem`),
3. buduje payload JSON dokładnie w formacie, jakiego oczekuje AWTRIX (`draw`, `icon`, `overlay`, ...),
4. wysyła go do każdego skonfigurowanego urządzenia (HTTP albo MQTT) na custom app `<app_topic>` oraz `<app_topic>_sun`.

## Czego potrzebujesz

- Współrzędne (lat/lon) miejsca, dla którego ma być pogoda.
- Adresy IP Twoich AWTRIX-ów w sieci lokalnej (transport HTTP, domyślny) **albo** broker MQTT + bazowe topiki urządzeń (transport MQTT).
- Jeśli wybierzesz OpenWeatherMap: darmowy klucz API z openweathermap.org (One Call API 3.0 - darmowy limit 1000 wywołań/dzień, ale przy rejestracji OWM prosi o dane karty; jeśli to przeszkadza, zostań przy Open-Meteo, które nie wymaga żadnej rejestracji).
- Ikony (`w-clear-night`, `w-sunny` itd.) muszą być wgrane na AWTRIX - użyj skryptu `upload_icon.sh` z repo jeeftor, jeśli jeszcze tego nie zrobiłeś.

## Konfiguracja

```bash
cp config.example.yaml config.yaml
# edytuj: location.latitude/longitude, weather.provider, awtrix.devices, ...
```

### Wybór dostawcy pogody

```yaml
weather:
  provider: "open-meteo"        # domyślny, bez klucza
  # provider: "openweathermap"        # One Call API 3.0 - wymaga klucza I osobnej subskrypcji
  # provider: "openweathermap-free"   # klasyczne endpointy 2.5 - wymaga tylko klucza, bez subskrypcji
  # openweathermap_api_key: "..."   # albo zmienna środowiskowa OWM_API_KEY
```

**Ważne przy OpenWeatherMap (`openweathermap`, One Call API 3.0):** sam klucz API
to za mało - trzeba dodatkowo aktywować darmową subskrypcję "One Call by Call"
na [openweathermap.org/api/one-call-3](https://openweathermap.org/api/one-call-3)
(przycisk "Subscribe" przy planie darmowym, 1000 wywołań/dzień). Bez tego
dostaniesz `401 Unauthorized`, nawet z poprawnym kluczem - a aktywacja subskrypcji
potrafi zająć do 2h. Jeśli nie chcesz się w to bawić, użyj `openweathermap-free`
(te same darmowe konto/klucz, klasyczne `/data/2.5` API, bez subskrypcji) -
jedyny kompromis to prognoza co 3h zamiast co godzinę (u nas i tak liniowo
interpolowana do rozdzielczości godzinowej, więc na wyświetlaczu wygląda
praktycznie tak samo).

Wszyscy trzej dostawcy zwracają temperaturę + prognozę godzinową znormalizowaną do tego
samego zestawu warunków pogodowych (`sunny`, `clear-night`, `cloudy`, `rainy`,
`pouring`, `snowy`, `lightning`, ... - taki sam zestaw jak w oryginalnym
blueprincie HA), więc reszta logiki (ikony, kolory, overlay) działa identycznie
niezależnie od wybranego providera.

### Transport do AWTRIX

```yaml
awtrix:
  transport: "http"     # domyślny - bez MQTT
  devices:
    - "192.168.1.50"    # adresy IP AWTRIX-ów
```

albo, jeśli wolisz MQTT:

```yaml
awtrix:
  transport: "mqtt"
  devices:
    - "awtrix_abcdef"   # bazowe topiki MQTT urządzeń
  mqtt:
    host: "127.0.0.1"
    username: ""
    password: ""
```

Sekrety (klucz OWM, hasło MQTT) możesz zamiast w pliku podać przez zmienne
środowiskowe: `OWM_API_KEY`, `MQTT_HOST`, `MQTT_PORT`, `MQTT_USERNAME`, `MQTT_PASSWORD`.

### Skala kolorów (color_matrix)

Domyślnie w `config.example.yaml` jest skala Celsjusza. Dla Fahrenheita:

```yaml
weather:
  units: "imperial"
  color_matrix:
    "0": "#FEC4FF"
    "10": "#D977DF"
    "20": "#9545BC"
    "30": "#4B379C"
    "40": "#31B8DB"
    "50": "#31DB8B"
    "60": "#6ED228"
    "70": "#FFFF28"
    "80": "#F87E27"
    "90": "#CF3927"
    "100": "#A12527"
```

## Jak często pytany jest dostawca pogody

Główna pętla chodzi co `poll_interval_seconds` (domyślnie **60 s**) - w każdym
cyklu odświeżamy księżyc/słońce i wysyłamy do AWTRIX-a. Samo API pogodowe jest
jednak cache'owane osobno: realnie pytane co `weather.refresh_seconds`
(domyślnie **300 s / 5 min**), między tym używane są dane z cache.

Dlaczego osobno: prognoza godzinowa i tak nie zmienia się co minutę, a przy
OpenWeatherMap (darmowy limit **1000 zapytań/dzień**) odpytywanie co 60s dałoby
1440 zapytań/dzień - czyli ponad limit. Przy domyślnym `refresh_seconds: 300`
wychodzi ok. 288 zapytań/dzień - bezpiecznie. Open-Meteo ma dużo wyższy
darmowy limit, więc tam można śmiało zejść z `refresh_seconds` niżej, jeśli
zależy Ci na szybszej reakcji na zmianę pogody.

## Kolor tekstu temperatury

Kolor cyfr temperatury (i kropek prognozy na dole) liczony jest **wyłącznie
na podstawie aktualnej wartości temperatury** przez interpolację w
`weather.color_matrix` - nie ma żadnego związku z aktualną ikoną/warunkiem
pogodowym (`sunny` nie "wymusza" żółtego). Jeśli kolor wygląda źle, najczęstsza
przyczyna to **niedopasowanie skali `color_matrix` do `weather.units`** -
np. zostawiona skala Fahrenheita (0-100) przy `units: metric` (wtedy
temperatura w Celsjuszach jest interpolowana względem progów zaprojektowanych
dla Fahrenheita i wychodzi zupełnie inny kolor niż oczekiwany).

Żeby to złapać, przy starcie skrypt sam to sprawdza i ostrzega w logu:

```
WARNING weather.color_matrix wygląda na skalę Fahrenheita (zakres 0..100) a
weather.units=metric (Celsjusz) - kolory temperatury będą źle dobrane. [...]
```

Jeśli dalej coś nie gra, uruchom z `-v` (log DEBUG) - każdy cykl loguje
dokładną wartość temperatury i wyliczony kolor:

```
DEBUG temp=21.0 (units=metric) -> kolor tekstu=#FFFF28 | warunek=sunny -> ikona=w-sunny
```

i porównaj to ręcznie z `weather.color_matrix` w swoim `config.yaml`.

## METAR - prawdziwy pomiar zamiast modelu (opcjonalnie)

Open-Meteo i OpenWeatherMap dają dane **modelowe** (wyliczone przez model
pogodowy). Jeśli wolisz, żeby akurat **bieżąca temperatura i ciśnienie**
(te dwie liczby na wyświetlaczu) pochodziły z prawdziwego pomiaru najbliższej
stacji lotniskowej (METAR) zamiast z modelu, włącz override przez
[AVWX REST API](https://avwx.rest) (wymaga darmowego klucza):

```yaml
weather:
  provider: "openweathermap-free"   # ikona + prognoza godzinowa - bez zmian
  metar_override:
    enabled: true
    station: "EPWA"                  # kod ICAO najbliższej stacji
    avwx_api_key: "..."               # albo zmienna środowiskowa AVWX_API_KEY
```

**Co się dokładnie dzieje:** ikona pogody i prognoza godzinowa (kolorowy pasek
na dole) zawsze pochodzą z `weather.provider` - METAR nie daje prognozy, tylko
bieżący pomiar. Override podmienia wyłącznie temperaturę i ciśnienie na świeży
odczyt ze stacji. Jeśli AVWX akurat nie odpowie (limit, awaria), skrypt **nie
wywala się** - loguje `WARNING` i po prostu zostaje przy wartościach z
głównego providera dla tego cyklu.

METAR i tak aktualizuje się na stacji zwykle raz na godzinę, więc domyślny
`weather.metar_override.refresh_seconds: 900` (15 min) to rozsądny punkt
startowy - **to osobne ustawienie, niezależne od `weather.refresh_seconds`**
(które kontroluje tylko główny provider, OWM/Open-Meteo). Możesz mieć np.
prognozę odświeżaną co 5 min, a METAR co 15 min, albo odwrotnie - jak wolisz.

Jednostki: temperatura w depeszy METAR jest zawsze w Celsjuszach (bez
dwuznaczności). Ciśnienie bywa w hPa (`Q1013`, stacje europejskie) albo inHg
(`A3005`, stacje północnoamerykańskie) - konwertujemy automatycznie do hPa
niezależnie od tego, co raportuje konkretna stacja.

### Bieżące zjawiska pogodowe (SHRA, TSRA, FG...) - osobna appka

METAR zgłasza też bieżące zjawiska (`SHRA` - przelotny deszcz, `TSRA` -
burza z deszczem, `FG` - mgła, `SN` - śnieg, itd.) w polu `wx_codes` - to
przychodzi w tym samym zapytaniu co temperatura/ciśnienie, więc nie kosztuje
dodatkowego wywołania API. Domyślnie włączone (`show_wx_alert: true`, wymaga
`metar_override.enabled: true`) - osobna appka (`jeef_weather_wx`) pokazuje
opis zjawiska (np. "Rain Showers") na bursztynowo, i **znika automatycznie**,
gdy zjawisko ustąpi (np. przelotny deszcz się skończył) - tak samo jak appka
wschodu/zachodu słońca.

Wyłączenie tylko tej części (zostawiając override temp/ciśnienia):
```yaml
weather:
  metar_override:
    show_wx_alert: false
```

## Ciśnienie atmosferyczne (opcjonalne, osobna appka)

Domyślnie wyłączone. Włączasz przez:

```yaml
pressure:
  enabled: true
```

Efekt: osobna custom app na AWTRIX (domyślnie `jeef_pressure`) pokazująca
aktualne ciśnienie + strzałkę trendu, jako zwykły tekst (`"1013 H ^"`) - `H`
zamiast `hPa`, żeby było krócej i zostało miejsce na strzałkę, gdy dane
trendu są już dostępne. Jeśli tekst i tak nie zmieści się na 32px ekranu,
AWTRIX przewinie go automatycznie (scroll) - to zachowanie samego firmware'u,
nie sterujemy tym z poziomu skryptu.

Kolor **liczby** ciśnienia zależy od poziomu (progi konfigurowalne):

- poniżej `pressure.low_hpa` (domyślnie 1000 hPa) - `low_color` (niebieski)
- między progami - `normal_color` (biały)
- powyżej `pressure.high_hpa` (domyślnie 1020 hPa) - `high_color` (bursztynowy)

Kolor **strzałki trendu** (osobno od liczby):

- `^` (zielony) - rośnie
- `v` (czerwony) - spada
- `=` (szary) - stabilne (zmiana mniejsza niż 1 hPa w oknie czasu)
- brak strzałki - zaraz po starcie skryptu, historia jeszcze za krótka żeby
  ocenić trend

**Skąd bierzemy trend:** żaden z dostawców pogody nie zwraca "trendu" wprost
- porównujemy aktualny odczyt z odczytem sprzed `pressure.trend_window_hours`
(domyślnie 3h) z własnej, trzymanej w pamięci historii. Historia żyje tylko
w RAM procesu - restart kontenera zeruje ją i trend wraca na chwilę do "brak
danych", dopóki nie zbierze się znowu przynajmniej połowa okna.

Pełna sekcja konfiguracji:

```yaml
pressure:
  enabled: false
  app_topic: "jeef_pressure"
  trend_window_hours: 3
  message_duration: 30
  low_hpa: 1000
  high_hpa: 1020
  low_color: "#4FA8E8"
  normal_color: "#FFFFFF"
  high_color: "#F2A93B"
```

## Walidacja i automatyczne wgrywanie ikon

Przy każdym starcie (transport `http`) skrypt pyta urządzenie o listę plików w
folderze `/ICONS` (ten sam endpoint, którego używa wbudowany file manager pod
`http://<ip>/edit`) i porównuje ją z ikonami wpisanymi w `weather.icons`.

Domyślnie tylko o tym informuje w logu:

```
WARNING 192.168.1.50: brakuje 3 ikon na urządzeniu (folder /ICONS): w-rainy, w-sunny, w-pouring.
```

Jeśli ustawisz `awtrix.auto_upload_missing_icons: true`, brakujące ikony
zostaną **automatycznie pobrane i wgrane** - z tego samego źródła, z którego
korzystał oryginalny `upload_icon.sh` z repo jeeftor
(`icons/weather/*.gif` w [jeeftor/HomeAssistant](https://github.com/jeeftor/HomeAssistant)),
tym samym sposobem co ten skrypt: `POST /edit` (multipart, pole `file`, docelowa
ścieżka `/ICONS/<nazwa>.gif` podana w nazwie pliku).

Możesz to też zrobić ręcznie, jednorazowo, bez uruchamiania całej aplikacji:

```bash
python upload_icons.py -c config.yaml            # wgraj tylko brakujące
python upload_icons.py -c config.yaml --all       # wgraj/nadpisz wszystkie
python upload_icons.py -c config.yaml --device 192.168.1.51   # tylko jedno urządzenie
```

Uwagi:
- Działa tylko dla domyślnego zestawu ikon `w-*` (taki jest w
  `config.example.yaml`) - jeśli wpiszesz własne nazwy ikon, których nie ma w
  repo jeeftor, dostaniesz warning "wgraj ją ręcznie".
- Sam listing `/edit?list=` jest "best effort" - format nie jest formalnie
  udokumentowany w API AWTRIX3. Jeśli się nie powiedzie, dostajesz jedno
  ostrzeżenie i skrypt jedzie dalej normalnie - to nie blokuje wysyłki pogody.
- Numeryczne ID ikon (podmiana `clear-night` na fazę księżyca) nie są
  sprawdzane ani uploadowane - AWTRIX pobiera je sam na żądanie z LaMetric.
- Dla transportu `mqtt` walidacja/upload są pomijane (nie mamy adresu IP) -
  użyj oryginalnego `upload_icon.sh` albo web UI urządzenia.
- Wyłączenie samej walidacji: `awtrix.check_icons_on_start: false`.

## Uruchomienie z logami DEBUG (`-v`) w Dockerze

Trzy sposoby, od najwygodniejszego:

1. **Zmienna środowiskowa** (nic nie trzeba przebudowywać) - w `docker-compose.yml`
   ustaw `LOG_LEVEL: "DEBUG"` i zrestartuj:
   ```bash
   docker compose up -d
   docker compose logs -f
   ```
   Wróć do `LOG_LEVEL: "INFO"` i znów zrestartuj, gdy skończysz diagnozować.

2. **Jednorazowo, bez zmiany plików** - tymczasowy kontener z `-v`, log leci na ekran:
   ```bash
   docker compose run --rm awtrix-weather python main.py -c /app/config/config.yaml -v
   ```
   Zatrzymujesz Ctrl+C, kontener sam się usuwa (`--rm`).

3. Lokalnie bez Dockera: `python main.py -c config.yaml -v` (patrz sekcja wyżej).

## Uruchomienie lokalnie (bez Dockera)

```bash
pip install -r requirements.txt
python main.py -c config.yaml -v
```

## Uruchomienie w Dockerze

```bash
docker compose up -d --build
docker compose logs -f
```

`config.yaml` jest montowany jako wolumen (read-only), więc zmiany w nim
wymagają tylko restartu kontenera (`docker compose restart`).

## Czym się różni od oryginalnego blueprintu HA

- Reaguje na interwał (`poll_interval_seconds`), nie na zdarzenie zmiany stanu encji pogody w HA - przy 60s pętli różnica w praktyce jest niezauważalna.
- Poprawiony (względem oryginału) warunek pokazywania księżyca zamiast ikony `clear-night`: w blueprincie porównanie było z `clear_night` (podkreślnik), a faktyczny stan pogodowy to `clear-night` (myślnik) - ta gałąź w oryginale nigdy się nie uruchamiała. Tutaj naprawione na myślnik. Żeby wrócić do zachowania 1:1 z oryginałem, zmień w `awtrix_weather/render.py` porównanie z powrotem na `"clear_night"`.
- Interpolacja koloru temperatura→kolor: zachowana wiernie łącznie z tym, że dokładne trafienie w próg z `color_matrix` i tak przechodzi przez interpolację z sąsiednim progiem (tak zachowywał się oryginalny szablon Jinja - patrz komentarz w `awtrix_weather/color.py`).
- Wschody/zachody i faza księżyca liczone lokalnie przez `ephem` zamiast brane z encji HA - wartości powinny być praktycznie identyczne (ephem uwzględnia standardową refrakcję atmosferyczną, tak jak komponent `sun` w HA), ale przy bardzo dokładnych porównaniach mogą się różnić o pojedyncze minuty.

## Obsługa błędów

Wszystkie błędy trafiają do logu na poziomie `ERROR` z pełnym tracebackiem
(`log.exception`/`exc_info=True`) - widoczne zawsze, niezależnie od
`LOG_LEVEL`/`-v`. Konkretnie:

- Błąd dostawcy pogody (sieć, zły klucz, limit) przerywa cały cykl - próba
  ponownie za `poll_interval_seconds`.
- Błąd wysyłki do **jednego** urządzenia AWTRIX **nie blokuje pozostałych** -
  każde urządzenie ma własny `try/except`, więc jedno padnięte urządzenie nie
  psuje aktualizacji reszty (ani appki ciśnienia) w tym samym cyklu.
- Błąd METAR-u (AVWX) nie blokuje niczego - `WARNING` w logu, ciche
  przełączenie z powrotem na dane z głównego dostawcy pogody na ten cykl.
- Błąd walidacji/uploadu ikon jest całkowicie odizolowany od reszty aplikacji.

## Struktura

```
main.py                          - punkt wejścia (CLI)
upload_icons.py                    - samodzielne (re)wgrywanie ikon, bez uruchamiania całej aplikacji
awtrix_weather/
  config.py                       - wczytywanie config.yaml + zmienne środowiskowe
  weather/
    base.py                        - wspólny interfejs dostawcy pogody
    caching.py                      - cache providera (weather.refresh_seconds)
    open_meteo.py                   - dostawca Open-Meteo (domyślny)
    openweathermap.py                - dostawca OpenWeatherMap (One Call API 3.0)
    openweathermap_free.py            - dostawca OpenWeatherMap (klasyczne /data/2.5, bez subskrypcji)
  astro.py                          - słońce i księżyc liczone lokalnie (ephem)
  metar.py                           - opcjonalny override temp/ciśnienia z prawdziwego METAR (AVWX)
  sanity_check.py                    - wykrywanie niedopasowania color_matrix do units
  color.py                          - interpolacja koloru wg temperatury
  moon.py                           - bitmapy faz księżyca + ikony clear-night
  icons.py                          - mapowanie warunku pogody -> overlay animacji
  text.py                           - szerokość/centrowanie tekstu na matrycy
  sun_event.py                      - komunikat wschód/zachód słońca
  pressure.py                        - trend ciśnienia (własna historia) + payload
  icon_check.py                       - walidacja przy starcie, czy ikony są wgrane na urządzeniu
  icon_upload.py                       - pobieranie ikon z repo jeeftor i wgrywanie ich na AWTRIX
  render.py                          - spina wszystko w payload JSON dla AWTRIX
  awtrix_client.py                    - wysyłka HTTP (domyślnie) albo MQTT
  app.py                               - pętla główna
```

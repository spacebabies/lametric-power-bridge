# LaMetric Power Bridge - Developer Documentation

Dit document beschrijft de architectuur en ontwikkelingsrichtlijnen voor toekomstige AI agents (Claude Code) en menselijke developers.

---

## Architectuur Overzicht

LaMetric Power Bridge is gebouwd met een **pluggable architecture** die duidelijk scheidt tussen:

1. **Ingress (Sources)**: Databronnen voor power metingen
2. **Business Logic**: Data transformatie en formatting
3. **Egress (Sinks)**: Output naar LaMetric Time device

```
┌─────────────────────────────────────────────────────────────┐
│                    bridge.py (43 regels)                    │
│                     Orchestrator                            │
│                                                             │
│  1. Detect/select source (auto of --source CLI arg)        │
│  2. await source.connect()                                  │
│  3. async for reading in source.stream()                   │
│  4. await push_to_lametric(reading)                        │
└─────────────────────────────────────────────────────────────┘
           │                                  │
           ▼                                  ▼
┌──────────────────────┐          ┌──────────────────────┐
│   sources/           │          │   sinks/             │
│   (Ingress)          │          │   (Egress)           │
├──────────────────────┤          ├──────────────────────┤
│ base.py              │          │ lametric.py          │
│ - PowerReading       │─────────▶│ - push_to_lametric() │
│ - PowerSource        │          │ - HTTP POST          │
│   Protocol           │          │ - Icon selection     │
│                      │          │ - kW formatting      │
│ tibber.py            │          └──────────────────────┘
│ - TibberSource       │
│                      │          ┌──────────────────────┐
│ homewizard_v1.py     │          │   tests/             │
│ - HomeWizardV1Source │          ├──────────────────────┤
│   (v1 API - HTTP)    │          │ test_lametric.py     │
│                      │          │ test_tibber.py       │
│ homewizard_v2.py     │          │ test_homewizard_v1.py│
│ - HomeWizardV2Source │          │ conftest.py          │
│   (v2 API - TODO)    │          └──────────────────────┘
│                      │
│ p1_serial.py         │
│ - P1SerialSource     │
│   (TODO)             │
└──────────────────────┘
```

---

## Core Concepts

### 1. PowerReading Dataclass

Uniform data contract tussen alle sources en sinks:

```python
@dataclass
class PowerReading:
    power_watts: float      # Positive = consuming, negative = producing
    timestamp: str | None   # ISO8601, optional
```

### 2. PowerSource Protocol

Duck-typed interface (geen ABC, geen gedwongen inheritance):

```python
class PowerSource(Protocol):
    async def connect(self) -> None:
        """Bootstrap: auth, discovery, setup"""
        ...

    async def stream(self) -> AsyncIterator[PowerReading]:
        """Yield PowerReading objecten, handle auto-reconnect"""
        ...
```

**Waarom Protocol?**
- Expliciete interface zonder boilerplate
- Duck typing blijft werken
- Type checking met mypy/pyright
- Pythonic (geen gedwongen `class Foo(PowerSource)`)

### 3. Context Manager Pattern

Alle sources implementeren async context manager voor automatic resource cleanup:

```python
async with HomeWizardV1Source(host="192.168.2.87") as source:
    async for reading in source.stream():
        await push_to_lametric(reading)
# Client automatisch geclosed bij exit
```

**Voordelen**:
- Gegarandeerde cleanup (httpx client, websockets, etc)
- Pythonic async pattern
- Geen handmatige `aclose()` calls nodig
- Werkt ook met oude `await source.connect()` pattern (backwards compatible)

**Implementatie**:
```python
class YourSource:
    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # Cleanup resources (close clients, etc)
        if self.client:
            await self.client.aclose()
```

### 4. Single Responsibility

- **Sources**: Alleen data ophalen en converteren naar PowerReading
- **Sinks**: Alleen data formatteren en versturen
- **Bridge**: Alleen orchestratie (geen business logic)

---

## Bestandsstructuur

```
lametric-power-bridge/
├── bridge.py                    # Orchestrator (43 regels)
├── sources/                     # Ingress modules
│   ├── __init__.py
│   ├── base.py                 # PowerReading + PowerSource Protocol
│   ├── tibber.py               # Tibber WebSocket implementatie
│   ├── homewizard_v1.py        # HomeWizard P1 Meter (v1 HTTP API)
│   ├── homewizard_v2.py        # HomeWizard P1 Meter (v2 WebSocket - TODO)
│   └── p1_serial.py            # DSMR P1 Serial (TODO)
├── sinks/
│   ├── __init__.py
│   └── lametric.py             # LaMetric formatting + HTTP push
├── tests/
│   ├── __init__.py
│   ├── conftest.py             # pytest fixtures
│   ├── test_lametric.py        # Sink tests (6 tests)
│   ├── test_tibber.py          # Tibber source tests (3 tests)
│   ├── test_homewizard_v1.py   # HomeWizard P1 v1 tests (6 tests)
│   └── test_bridge.py          # Bridge logic tests (3 tests)
├── lametric-power-bridge.env    # Configuration (all sources)
├── requirements.txt
├── requirements-dev.txt
└── README.md
```

---

## Multi-Source Selection

### Command Line Source Selection

Bridge.py vereist expliciete source selectie via `--source` argument:

```bash
# Tibber (default als geen --source opgegeven)
python bridge.py
python bridge.py --source=tibber

# HomeWizard v1 API (HTTP Polling)
python bridge.py --source=homewizard-v1

# HomeWizard v2 API (WebSocket - TODO)
python bridge.py --source=homewizard-v2

# P1 Serial (DSMR via USB - TODO)
python bridge.py --source=p1-serial
```

**Belangrijk**:
- `--source` faalt HARD als configuratie mist (geen fallback)
- Alle sources gebruiken dezelfde `.env` file (`lametric-power-bridge.env`)
- Default is `tibber` voor backwards compatibility

### Implementatie Richtlijnen

De huidige `get_source()` functie in `bridge.py`:

```python
def get_source(source_name: str):
    """Initialize the selected power source with hard fail on misconfiguration"""
    if source_name == "tibber":
        token = os.getenv("TIBBER_TOKEN")
        if not token:
            logger.error("Tibber: TIBBER_TOKEN not configured in lametric-power-bridge.env")
            sys.exit(1)
        logger.info(f"Using source: Tibber")
        return TibberSource(token=token)
    elif source_name == "homewizard-v1":
        host = os.getenv("HOMEWIZARD_HOST")
        if not host:
            logger.error("HomeWizard P1: HOMEWIZARD_HOST not configured in lametric-power-bridge.env")
            sys.exit(1)
        logger.info(f"Using source: HomeWizard P1 (v1 API)")
        return HomeWizardV1Source(host=host)
    # elif source_name == "homewizard-v2":  # TODO
    # elif source_name == "p1-serial":      # TODO
    else:
        logger.error(f"Unknown source: {source_name}")
        sys.exit(1)
```

**Pattern voor nieuwe sources:**
1. Add `elif source_name == "your-source"` case
2. Load config van environment variable (uit `lametric-power-bridge.env`)
3. Hard fail met duidelijke error als config mist
4. Log welke source gebruikt wordt
5. Return geïnitialiseerde source instance

---

## Source Implementatie Gids

### Nieuwe Source Toevoegen

1. **Maak `sources/your_source.py`**
2. **Implementeer class met PowerSource interface**:
   ```python
   class YourSource:
       async def connect(self) -> None:
           # Bootstrap logica (auth, discovery, etc)
           pass

       async def stream(self) -> AsyncIterator[PowerReading]:
           # Yield PowerReading objecten
           while True:
               data = await self.fetch_data()
               yield PowerReading(
                   power_watts=data['power'],
                   timestamp=data.get('timestamp')
               )
   ```
3. **Schrijf tests in `tests/test_your_source.py`**
4. **Update `get_source()` in bridge.py** (add elif case + argparse choices)
5. **Update `lametric-power-bridge.env.example`** met nieuwe configuratie variabelen

### Bestaande Sources

#### Tibber (sources/tibber.py)

**Configuratie** (`lametric-power-bridge.env`):
```bash
TIBBER_TOKEN=your_api_token_here
```

**Implementatie**:
- `connect()`: HTTP POST naar GraphQL API voor WebSocket URL + home_id
- `stream()`: WebSocket met `graphql-transport-ws` protocol
- Auto-reconnect: Ingebouwd in `async for websocket in websockets.connect()`

**API Details**:
- Endpoint: `https://api.tibber.com/v1-beta/gql`
- WebSocket subprotocol: `graphql-transport-ws`
- Auth: Bearer token in connection_init payload
- Data: `liveMeasurement.power` (in Watts)

#### HomeWizard P1 v1 API (sources/homewizard_v1.py)

**Configuratie** (`lametric-power-bridge.env`):
```bash
HOMEWIZARD_HOST=192.168.2.87
```

**API Documentatie**: https://api-documentation.homewizard.com/docs/v1/measurement

**Implementatie**:
- `connect()`: Test connectivity met single HTTP GET, valideer `active_power_w` field
- `stream()`: HTTP polling naar `/api/v1/data` endpoint (1s interval default)
- Keep-alive: `httpx.AsyncClient` voor persistent connections
- Error handling: Exponential backoff voor device busy (429/503) states
- Data mapping: `active_power_w` → `PowerReading.power_watts`
- Timestamp: `None` (v1 API bevat geen timestamps)

**Features**:
- Retry logic met max retries (default: 3)
- Device busy detection (503 errors krijgen langere retry delay)
- Graceful handling van missing fields (device initializing)
- Configurable poll interval en timeout

**Opmerkingen**:
- Vriendelijk voor device: keep-alive voorkomt connection overhead
- v1 API is polling only (geen push/WebSocket)
- Alle fields zijn optioneel in API response

#### HomeWizard P1 v2 API (sources/homewizard_v2.py) - TODO

**Configuratie** (`lametric-power-bridge.env`):
```bash
HOMEWIZARD_HOST=192.168.1.xxx
```

**API Documentatie**: https://api-documentation.homewizard.com/docs/v2/websocket

**Implementatie TODO**:
- `connect()`: Mogelijk niet nodig (WebSocket direct beschikbaar)
- `stream()`: WebSocket naar `/api/v2/data` endpoint
- Data mapping: `active_power_w` → `PowerReading.power_watts`
- Timestamp: Mogelijk niet beschikbaar (gebruik `None` of genereer lokaal)

**Opmerkingen**:
- WebSocket protocol verschilt van Tibber (geen GraphQL)
- Check API docs voor exact message format
- Mogelijk dat v2 ook push updates heeft (versus polling)

#### P1 Serial (sources/p1_serial.py) - TODO

**Configuratie**:
- Hardcoded: `/dev/ttyUSB0` (voor nu)
- Toekomstig: `P1_SERIAL_DEVICE` env var voor flexibiliteit

**Implementatie TODO**:
- Dependency: `pyserial` (toevoegen aan requirements.txt)
- `connect()`: Open serial port (115200 baud, 8N1)
- `stream()`: Lees DSMR telegrams, parse met bestaande library
- Data mapping: Parse `1-0:1.7.0` (current power) → PowerReading
- Error handling: USB disconnect detection + reconnect

**DSMR Parsing**:
- Overweeg library: `dsmr_parser` (https://github.com/ndokter/dsmr_parser)
- Of minimale parser voor alleen power reading (geen overhead)

---

## Testing Strategie

### Test Filosofie

- **Unit tests**: Mock alle I/O (HTTP, WebSocket, Serial)
- **High-level tests**: Test business logic, niet implementatie details
- **No network**: `pytest-socket` blokkeert alle network calls (zie conftest.py)

### Test Coverage

**Minimum per source**:
1. `connect()` success scenario (mock bootstrap)
2. `connect()` failure scenario (missing config, API down)
3. `stream()` happy path (mock data → PowerReading)

**Sink tests**:
- Test alle edge cases: positief/negatief, kW conversie, rounding

### Fixtures (tests/conftest.py)

```python
@pytest.fixture
def sample_reading():
    """Standaard PowerReading voor tests"""
    return PowerReading(power_watts=1500.0, timestamp="2025-12-26T18:00:00")

@pytest.fixture
def mock_tibber_messages():
    """Voorbeeld Tibber WebSocket messages"""
    return {
        "connection_ack": {"type": "connection_ack"},
        "next": {
            "type": "next",
            "payload": {
                "data": {
                    "liveMeasurement": {
                        "power": 1500,
                        "timestamp": "2025-12-26T18:00:00"
                    }
                }
            }
        },
        "error": {"type": "error", "payload": ["Error message"]}
    }
```

**Conventies**:
- Test functies: `test_<module>_<function>_<scenario>`
- Mock alleen wat nodig is (geen over-mocking)
- Use `mocker.patch()` voor I/O, niet `@patch` decorator

---

## Code Style & Conventies

### Python Style

- **Type hints**: Gebruik waar relevant (`PowerReading`, `AsyncIterator`, etc)
- **Docstrings**: Alleen voor publieke API, niet voor obvieuze functies
- **Logging**: Gebruik logger, niet print()
- **Error handling**: Log errors, gebruik sys.exit(1) voor fatale fouten

### Imports

```python
# Standaard library
import asyncio
import logging
import os

# Third-party
import requests
import websockets
from dotenv import load_dotenv

# Local
from sources.base import PowerReading
from sinks.lametric import push_to_lametric
```

### Naming Conventions

- **Classes**: `PascalCase` (`TibberSource`, `PowerReading`)
- **Functions**: `snake_case` (`push_to_lametric`, `detect_source`)
- **Constants**: `UPPER_SNAKE_CASE` (`TIBBER_TOKEN`, `ICON_POWER`)
- **Private functions**: `_leading_underscore` (`_perform_http_request`)

### Async Conventions

- **Always await**: Geen `asyncio.create_task()` zonder await
- **Auto-reconnect**: Implementeer in source, niet in bridge
- **Error handling**: Try/except in stream loop, await asyncio.sleep(5) na errors

---

## Deployment

### Systemd Service

**Locatie**: `/etc/systemd/system/lametric-power-bridge.service`

```ini
[Service]
ExecStart=/path/to/.venv/bin/python /path/to/bridge.py
# GEEN --source argument (auto-detect is default)
```

**Waarom geen `--source` in service?**
- Auto-detect werkt out-of-the-box voor meeste gebruikers
- Bij hardware wijziging (bijv. USB kabel toevoegen) werkt het automatisch
- Expliciete `--source` alleen voor debugging/testing

### Environment Variables

**Locatie**: Single `.env` file voor alle configuratie

- `lametric-power-bridge.env`: Bevat alle configuratie variabelen
- Voorbeeld bestand: `lametric-power-bridge.env.example`

**Laden in bridge.py**:
```python
# Load configuration from single .env file
load_dotenv("lametric-power-bridge.env")
```

**Variabelen**:
- `TIBBER_TOKEN`: Tibber API token (verplicht voor `--source=tibber`)
- `HOMEWIZARD_HOST`: HomeWizard P1 host IP (verplicht voor `--source=homewizard-v1`)
- `LAMETRIC_URL`: LaMetric Push URL (optioneel - auto-discovery via SSDP, alleen handmatig configureren bij 0 of 2+ devices)
- `LAMETRIC_API_KEY`: LaMetric API key (verplicht voor alle sources)

---

## Refactoring History

Deze architectuur is het resultaat van een stapsgewijze refactoring:

### STAP 1: Extract LaMetric Sink (commit 41da458)
- Scheiding egress logica van bridge.py
- Maak `sinks/lametric.py`
- bridge.py: 201 → 146 regels (-55)

### STAP 2: Introduceer PowerReading (commit d876461)
- Uniform data contract tussen sources en sinks
- Maak `sources/base.py` met PowerReading dataclass + PowerSource Protocol
- Update alle code om PowerReading te gebruiken

### STAP 3: Extract Tibber Source (commit df40ac1)
- Isoleer Tibber logica in `sources/tibber.py`
- bridge.py: 199 → 43 regels (-78%!)
- Bridge wordt source-agnostisch orchestrator

### STAP 4: Add Tibber Tests (commit 5d1eb9c)
- 3 high-level tests voor TibberSource
- Total: 9 tests (6 lametric + 3 tibber)

### STAP 5: CLI Source Selection (commits 46fa5a5, d02d186)
- Add `--source` CLI argument met argparse
- Implementeer `get_source()` factory functie met config validatie
- Multi-env loading (tibber.env + homewizard.env)
- Hard fail met duidelijke errors bij misconfiguratie
- 3 nieuwe tests voor bridge logica
- Total: 12 tests (6 lametric + 3 tibber + 3 bridge)

**Resultaat**: Van 259-regel monoliet naar modulaire architectuur met CLI support en volledige test coverage.

---

## Toekomstige Werk (TODO)

### Prio 1: HomeWizard P1 v2 WebSocket API (sources/homewizard_v2.py)
1. Implementeer `sources/homewizard_v2.py`
2. WebSocket naar `/api/v2/data` (zie API docs)
3. Maak `tests/test_homewizard_v2.py`
4. Add nieuwe config vars aan `lametric-power-bridge.env.example`
5. Add `"homewizard-v2"` to choices in bridge.py
6. Add `elif source_name == "homewizard-v2"` case in `get_source()`

### Prio 2: P1 Serial Source (sources/p1_serial.py)
1. Add `pyserial` dependency
2. Implementeer `sources/p1_serial.py`
3. DSMR telegram parsing (gebruik library of minimale parser)
4. USB disconnect handling + auto-reconnect
5. Maak `tests/test_p1_serial.py`

### Prio 3: Multi-frame Support (optioneel)
- Extend PowerReading naar MeterReading met gas/prijs data?
- Update LaMetric sink om meerdere frames te sturen
- Configureerbaar: welke metingen tonen?

### Prio 4: Source Detection Improvements
- P1 Serial: Auto-scan `/dev/serial/by-id/*dsmr*` pattern
- HomeWizard: mDNS discovery als fallback
- Command: `python bridge.py --list-sources` om beschikbare sources te tonen

---

## Troubleshooting

### Tests falen met SocketBlockedError

**Oorzaak**: `pytest-socket` blokkeert alle network calls (zie `tests/conftest.py`).

**Oplossing**: Mock alle HTTP/WebSocket calls met `pytest-mock`.

### Source niet gedetecteerd

**Debug**:
```bash
# Check welke env vars geladen zijn
python -c "from dotenv import load_dotenv; load_dotenv('lametric-power-bridge.env'); import os; print(os.getenv('TIBBER_TOKEN'))"

# Check serial device
ls -la /dev/ttyUSB*

# Check HomeWizard host
python -c "from dotenv import load_dotenv; load_dotenv('lametric-power-bridge.env'); import os; print(os.getenv('HOMEWIZARD_HOST'))"
```

### Systemd service start niet

**Check logs**:
```bash
sudo journalctl -u lametric-power-bridge -f
```

**Common issues**:
- `.venv` path incorrect in service file
- `lametric-power-bridge.env` niet readable door service user
- Config variabelen niet correct gezet in `lametric-power-bridge.env`

---

## AI Agent Guidelines

Als je een AI agent bent (Claude Code) die aan dit project werkt:

### Development Workflow (VERPLICHT) 🔄

**Voor ELKE code wijziging, volg deze stappen:**

1. **Maak een feature branch**
   ```bash
   git checkout -b feature/descriptive-name
   ```
   - Werk NOOIT direct op main
   - Branch naam: `feature/`, `fix/`, of `refactor/` prefix

2. **Maak de wijzigingen**
   - Volg de architectuur principes (zie boven)
   - **Commit early, commit often** op de feature branch
   - Houd commits klein en gefocust (één feature/fix per commit)

3. **Schrijf/update tests**
   - Nieuwe features: Voeg tests toe (minimum 1 test)
   - Bug fixes: Voeg regression test toe
   - Refactoring: Bestaande tests moeten blijven werken

4. **Run tests en commit**
   ```bash
   pytest tests/ -v
   git add -A
   git commit -m "descriptive message"
   ```
   - Alle tests MOETEN groen zijn voor commit
   - **COMMIT OP BRANCH = GEWENST** (dit is niet main!)
   - Gebruik beschrijvende commit messages

5. **Vraag gebruiker om review/merge**
   - Presenteer de wijzigingen
   - Leg uit wat je hebt gedaan
   - Laat gebruiker de branch mergen naar main

**Waarom deze workflow?**
- **Commits op branches zijn GEWENST**: dit is hoe git werkt
- **NOOIT commits op main**: gebruiker houdt controle over main branch
- Test failures worden vroeg gevangen
- Git history blijft clean en reviewable
- Eenvoudig om wijzigingen te reverteren indien nodig

**Git Policy Samenvatting**:
- ✅ **DO**: Commit op feature branches (frequent en vaak!)
- ❌ **DON'T**: Commit direct op main branch (never!)

### Tone and Style 🎭

**BELANGRIJK**: Dit project heeft een specifieke stem. Volg deze richtlijnen:

**Prose (README, .env.example, documentatie voor gebruikers)**:
- ✅ Gebruik **mild annoyance, sarcasm, en British humour**
- ✅ Referentie tone: Bestaande README.md (perfecte balans)
- ✅ Voorbeelden:
  - "An expensive pixel clock that has no business costing this much"
  - "It is almost 2026; please keep up"
  - "Do not let me catch you using nano"
  - "I am not your butler"
- ❌ Geen sycophantic/overdreven enthousiast taalgebruik
- ❌ Geen Amerikaanse corporate speak ("amazing!", "awesome!")

**Code Comments**:
- ✅ Neutraal en technisch
- ✅ Duidelijk en informatief
- ❌ **GEEN** sarcasme of humor in code comments
- ❌ **GEEN** humor in docstrings

**Commit Messages**:
- ✅ Professioneel en beschrijvend
- ❌ Geen humor (tenzij subtiel passend)

**Voorbeeld contrast**:
```python
# ✅ Code comment (neutral, technical)
# Create persistent HTTP client with keep-alive
self.client = httpx.AsyncClient(...)

# ✅ README prose (sarcastic, British)
"HTTP GET requests, sent every second, like a needy houseguest
checking if dinner is ready."
```

### DO's ✅

- **Commit early, commit often** op feature branches (na elke logische stap)
- **Tests schrijven** voor nieuwe sources (minimum 3 tests)
- **PowerSource Protocol volgen** voor nieuwe sources
- **Mock alle I/O** in tests (pytest-socket forceert dit)
- **Type hints gebruiken** waar relevant
- **Logging** gebruiken voor belangrijke events
- **Tone matchen**: Sarcasme in prose, neutral in code

### DON'Ts ❌

- **Geen over-engineering**: Houd het simpel (KISS)
- **Geen ABC's**: Gebruik Protocol voor interfaces
- **Geen network in tests**: pytest-socket blokkeert dit
- **Geen sys.exit() in sources**: Alleen in bootstrap (connect())
- **Geen werk op main branch**: Altijd feature branch gebruiken
- **Geen sycophantic taalgebruik**: README is droog/sarcastic, niet enthousiast
- **Geen humor in code comments**: Alleen in user-facing prose

### Best Practices

1. **Lees eerst de code**: Begrijp de architectuur voor je wijzigt
2. **Volg bestaande patterns**: Tibber is het referentie voorbeeld
3. **Test je werk**: `pytest tests/ -v` moet altijd groen zijn
4. **Kleine commits**: 1 feature/fix per commit
5. **Duidelijke commit messages**: Beschrijf wat en waarom

---

## Resources

### Documentatie
- **HomeWizard P1 API**: https://api-documentation.homewizard.com/docs/v2/websocket
- **Tibber GraphQL**: https://developer.tibber.com/docs/overview
- **DSMR Specificatie**: https://www.netbeheernederland.nl/dossiers/slimme-meter-15

### Dependencies
- **websockets**: AsyncIO WebSocket library
- **requests**: HTTP client voor bootstrap calls
- **httpx**: Modern async HTTP client voor polling sources (keep-alive support)
- **python-dotenv**: Environment variable loading
- **pytest-asyncio**: AsyncIO support in pytest
- **pytest-mock**: Mocking framework
- **pytest-socket**: Network blocking voor tests

### Project Links
- **GitHub**: https://github.com/spacebabies/lametric-power-bridge
- **License**: GPLv3 (no commercial closed-source use)

---

## Changelog

- **2026-01-01**: LaMetric Time SSDP auto-discovery toegevoegd (LAMETRIC_URL nu optioneel, handles DHCP lease renewals, 12 LaMetric tests total)
- **2025-12-28**: Consolidated .env files - all config in `lametric-power-bridge.env` (learning: separate files was over-engineering)
- **2025-12-28**: HomeWizard P1 v1 API toegevoegd (`--source=homewizard-v1`, HTTP polling, 18 tests total)
- **2025-12-28**: CLI source selection toegevoegd (STAP 5: `--source` argument, 12 tests total)
- **2025-12-26**: Stale data timeout monitoring toegevoegd (60s timeout, "-- W" indicator)
- **2025-12-26**: Development Workflow toegevoegd aan CLAUDE.md (verplicht feature branches)
- **2025-12-26**: Refactoring naar pluggable architecture (STAP 1-3)
- **2025-12-26**: Tibber tests toegevoegd (9 tests total: 6 lametric + 3 tibber)
- **2025-12-26**: CLAUDE.md documentatie geschreven

---

*Dit document evolueert met het project. Update bij significante architectuur wijzigingen.*

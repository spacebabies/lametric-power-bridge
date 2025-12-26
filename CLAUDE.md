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
│ homewizard_p1.py     │          │   tests/             │
│ - HomeWizardP1Source │          ├──────────────────────┤
│   (TODO)             │          │ test_lametric.py     │
│                      │          │ test_tibber.py       │
│ p1_serial.py         │          │ conftest.py          │
│ - P1SerialSource     │          └──────────────────────┘
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

### 3. Single Responsibility

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
│   ├── homewizard_p1.py        # HomeWizard P1 (TODO)
│   └── p1_serial.py            # DSMR P1 Serial (TODO)
├── sinks/
│   ├── __init__.py
│   └── lametric.py             # LaMetric formatting + HTTP push
├── tests/
│   ├── __init__.py
│   ├── conftest.py             # pytest fixtures
│   ├── test_lametric.py        # Sink tests (5 tests)
│   └── test_tibber.py          # Tibber source tests (3 tests)
├── tibber.env                   # Tibber config (backwards compatible)
├── homewizard.env               # HomeWizard config (TODO)
├── requirements.txt
├── requirements-dev.txt
└── README.md
```

---

## Multi-Source Detectie

### Auto-Detectie Volgorde

Bridge.py detecteert automatisch de **beste beschikbare source** met deze prioriteit:

1. **P1 Serial** (`/dev/ttyUSB0` aanwezig)
2. **HomeWizard P1** (`HOMEWIZARD_URL` in config)
3. **Tibber** (`TIBBER_TOKEN` in config)
4. **Geen match** → Hard fail met error

### Command Line Override

```bash
# Auto-detect (default)
python bridge.py

# Expliciete keuze (hard fail bij misconfiguratie)
python bridge.py --source=serial
python bridge.py --source=homewizard
python bridge.py --source=tibber
```

**Belangrijk**: Expliciete `--source` faalt HARD als configuratie mist. Geen fallback naar auto-detect.

### Implementatie Richtlijnen

```python
# Voorbeeld detect_source() functie:
async def detect_source(explicit_source: str | None = None):
    if explicit_source:
        # Hard fail bij misconfiguratie
        if explicit_source == 'serial':
            if not os.path.exists('/dev/ttyUSB0'):
                logger.error("P1 Serial: /dev/ttyUSB0 not found")
                sys.exit(1)
            return P1SerialSource(device='/dev/ttyUSB0')
        elif explicit_source == 'homewizard':
            url = os.getenv('HOMEWIZARD_URL')
            if not url:
                logger.error("HomeWizard: HOMEWIZARD_URL not configured")
                sys.exit(1)
            return HomeWizardP1Source(url=url)
        elif explicit_source == 'tibber':
            token = os.getenv('TIBBER_TOKEN')
            if not token:
                logger.error("Tibber: TIBBER_TOKEN not configured")
                sys.exit(1)
            return TibberSource(token=token)
    else:
        # Auto-detect met prioriteit
        if os.path.exists('/dev/ttyUSB0'):
            logger.info("Auto-detected: P1 Serial")
            return P1SerialSource(device='/dev/ttyUSB0')

        if os.getenv('HOMEWIZARD_URL'):
            logger.info("Auto-detected: HomeWizard P1")
            return HomeWizardP1Source(url=os.getenv('HOMEWIZARD_URL'))

        if os.getenv('TIBBER_TOKEN'):
            logger.info("Auto-detected: Tibber")
            return TibberSource(token=os.getenv('TIBBER_TOKEN'))

        logger.error("No power source found!")
        sys.exit(1)
```

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
4. **Update `detect_source()` in bridge.py**
5. **Maak `your_source.env.example` met configuratie template**

### Bestaande Sources

#### Tibber (sources/tibber.py)

**Configuratie** (`tibber.env`):
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

#### HomeWizard P1 (sources/homewizard_p1.py) - TODO

**Configuratie** (`homewizard.env`):
```bash
HOMEWIZARD_URL=ws://192.168.1.xxx/api/v2/data
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
- Mogelijk polling nodig (versus push updates)

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

**Locatie**: Per source een eigen `.env` file

- `tibber.env`: `TIBBER_TOKEN=...`
- `homewizard.env`: `HOMEWIZARD_URL=ws://...`
- Geen shared `.env` (voorkomt verwarring)

**Laden in bridge.py**:
```python
# Load alle mogelijke configs (ontbrekende files worden genegeerd)
load_dotenv("tibber.env")
load_dotenv("homewizard.env")
# Detectie functie checkt welke vars aanwezig zijn
```

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
- Total: 8 tests (5 lametric + 3 tibber)

**Resultaat**: Van 259-regel monoliet naar modulaire architectuur met duidelijke scheiding.

---

## Toekomstige Werk (TODO)

### Prio 1: HomeWizard P1 Source
1. Implementeer `sources/homewizard_p1.py`
2. WebSocket naar `/api/v2/data` (zie API docs)
3. Maak `tests/test_homewizard.py`
4. Maak `homewizard.env.example`
5. Update `detect_source()` in bridge.py

### Prio 2: P1 Serial Source
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
python -c "from dotenv import load_dotenv; load_dotenv('tibber.env'); import os; print(os.getenv('TIBBER_TOKEN'))"

# Check serial device
ls -la /dev/ttyUSB*

# Check HomeWizard URL
echo $HOMEWIZARD_URL
```

### Systemd service start niet

**Check logs**:
```bash
sudo journalctl -u lametric-power-bridge -f
```

**Common issues**:
- `.venv` path incorrect in service file
- `tibber.env` niet readable door service user
- TIBBER_TOKEN niet in environment (service moet env files laden)

---

## AI Agent Guidelines

Als je een AI agent bent (Claude Code) die aan dit project werkt:

### DO's ✅

- **Commit early, commit often** (na elke stap)
- **Tests schrijven** voor nieuwe sources (minimum 3 tests)
- **PowerSource Protocol volgen** voor nieuwe sources
- **Mock alle I/O** in tests (pytest-socket forceert dit)
- **Backwards compatibility** behouden (tibber.env blijft werken)
- **Type hints gebruiken** waar relevant
- **Logging** gebruiken voor belangrijke events

### DON'Ts ❌

- **Geen over-engineering**: Houd het simpel (KISS)
- **Geen ABC's**: Gebruik Protocol voor interfaces
- **Geen shared .env**: Elke source heeft eigen config file
- **Geen network in tests**: pytest-socket blokkeert dit
- **Geen breaking changes**: Backwards compatible blijven
- **Geen sys.exit() in sources**: Alleen in bootstrap (connect())
- **Geen auto-commit**: Gebruiker moet expliciet vragen

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
- **python-dotenv**: Environment variable loading
- **pytest-asyncio**: AsyncIO support in pytest
- **pytest-mock**: Mocking framework
- **pytest-socket**: Network blocking voor tests

### Project Links
- **GitHub**: https://github.com/spacebabies/lametric-power-bridge
- **License**: GPLv3 (no commercial closed-source use)

---

## Changelog

- **2025-12-26**: Refactoring naar pluggable architecture (STAP 1-3)
- **2025-12-26**: Tibber tests toegevoegd (8 tests total)
- **2025-12-26**: CLAUDE.md documentatie geschreven

---

*Dit document evolueert met het project. Update bij significante architectuur wijzigingen.*

# wattpilot-api

Async Python library for Fronius Wattpilot Wallbox devices.

Connects to Wattpilot EV chargers over WebSocket using a reverse-engineered API (the same protocol used by the official Wattpilot.Solar mobile app). Provides real-time property synchronization, an MQTT bridge, Home Assistant discovery, and an interactive CLI shell.

## Features

- **Fully async** — built on `asyncio` and `websockets`, compatible with Home Assistant
- **All Wattpilot hardware** — supports standard (V2) and Flex models via PBKDF2 and bcrypt authentication
- **388+ properties** — access every charger property in real time
- **MQTT bridge** — publish properties and subscribe to commands via `aiomqtt`
- **Home Assistant discovery** — automatic entity creation with proper device classes
- **Interactive shell** — async CLI with TAB completion via `prompt_toolkit`
- **Type-safe** — full type hints, `mypy --strict`, PEP 561 `py.typed` marker
- **100% test coverage** — 241 unit tests + 18 integration tests

## Requirements

- Python 3.12+
- Local network access to a Fronius Wattpilot charger

## Installation

```bash
pip install wattpilot-api
```

For development:

```bash
pip install -e ".[dev]"
```

## Quick Start

### As a library

```python
import asyncio
from wattpilot_api import Wattpilot, LoadMode

async def main():
    async with Wattpilot("192.168.1.100", "your_password") as wp:
        # Read properties
        print(f"Serial: {wp.serial}")
        print(f"Firmware: {wp.firmware}")
        print(f"Power: {wp.power:.2f} kW")
        print(f"Amperage: {wp.amp} A")
        print(f"Car connected: {wp.car_connected}")
        print(f"Mode: {LoadMode(wp.mode).name}")

        # Set charging amperage
        await wp.set_power(16)

        # Set charging mode
        await wp.set_mode(LoadMode.ECO)

        # Register a callback for property changes
        def on_change(name, value):
            print(f"{name} = {value}")

        unsub = wp.on_property_change(on_change)

        # Access all 388+ raw properties
        for key, value in sorted(wp.all_properties.items()):
            print(f"  {key} = {value}")

        unsub()  # unsubscribe when done

asyncio.run(main())
```

### Interactive shell

```bash
export WATTPILOT_HOST=192.168.1.100
export WATTPILOT_PASSWORD=your_password
wattpilotshell
```

### With MQTT and Home Assistant

```bash
export WATTPILOT_HOST=192.168.1.100
export WATTPILOT_PASSWORD=your_password
export MQTT_ENABLED=true
export MQTT_HOST=your_mqtt_broker
export HA_ENABLED=true
wattpilotshell
```

## Supported Hardware

| Device | Auth | Status |
|---|---|---|
| Wattpilot Home (V2) | PBKDF2 | Tested |
| Wattpilot Home FLEX 11 C6 | bcrypt | Supported |
| Wattpilot Home FLEX 22kW | bcrypt | Supported |
| Wattpilot (cloud via Fronius API) | PBKDF2 | Supported |

Authentication is auto-detected:
1. If the `authRequired` message includes a `hash` field, that algorithm is used
2. Otherwise, if `devicetype` is `wattpilot_flex`, bcrypt is used
3. Otherwise, PBKDF2 is used (default)

## API Reference

### Wattpilot Client

```python
from wattpilot_api import Wattpilot

# Constructor
wp = Wattpilot(
    host="192.168.1.100",
    password="your_password",
    serial=None,           # auto-detected from device
    cloud=False,           # True for Fronius cloud connection
    connect_timeout=30.0,  # seconds
    init_timeout=30.0,     # seconds
)

# Connect / disconnect
await wp.connect()
await wp.disconnect()

# Or use as async context manager
async with Wattpilot("192.168.1.100", "password") as wp:
    ...
```

### Properties

| Property | Type | Description |
|---|---|---|
| `wp.connected` | `bool` | Connection status |
| `wp.serial` | `str` | Device serial number |
| `wp.name` | `str` | Device name |
| `wp.manufacturer` | `str` | Manufacturer ("fronius") |
| `wp.device_type` | `str` | Device type ("wattpilot_V2", "wattpilot_flex") |
| `wp.version` | `str` | Firmware version |
| `wp.amp` | `int` | Current amperage setting |
| `wp.mode` | `int` | Charging mode (3=Default, 4=Eco, 5=NextTrip) |
| `wp.car_connected` | `int` | Car status (1=No car, 2=Charging, 3=Ready, 4=Complete) |
| `wp.allow_charging` | `bool` | Whether charging is allowed |
| `wp.voltage1/2/3` | `float` | Phase voltages |
| `wp.amps1/2/3` | `float` | Phase currents |
| `wp.power1/2/3` | `float` | Phase power (kW) |
| `wp.power` | `float` | Total power (kW) |
| `wp.frequency` | `float` | Grid frequency (Hz) |
| `wp.energy_counter_since_start` | `float` | Session energy (Wh) |
| `wp.energy_counter_total` | `float` | Lifetime energy (Wh) |
| `wp.error_state` | `int` | Error code |
| `wp.cable_type` | `int` | Cable capacity (A) |
| `wp.cable_lock` | `int` | Lock mode |
| `wp.access_state` | `int` | Access state |
| `wp.phases` | `list` | Phase configuration |
| `wp.all_properties` | `dict` | All 388+ raw properties |

### Commands

```python
await wp.set_power(16)                    # Set amperage (6-32)
await wp.set_mode(LoadMode.ECO)           # Set charging mode
await wp.set_property("fna", "MyCharger") # Set any writable property
```

### Callbacks

```python
# Sync or async callbacks supported
unsub = wp.on_property_change(lambda name, value: print(f"{name}={value}"))
unsub()  # unsubscribe

unsub = wp.on_message(lambda msg: print(msg["type"]))
unsub()
```

### Enums

```python
from wattpilot_api import LoadMode, CarStatus, ErrorState, AccessState, CableLockMode

LoadMode(wp.mode)           # LoadMode.DEFAULT / ECO / NEXTTRIP
CarStatus(wp.car_connected) # CarStatus.NO_CAR / CHARGING / READY / COMPLETE
```

### Exceptions

```python
from wattpilot_api import WattpilotError, AuthenticationError, ConnectionError

try:
    await wp.connect()
except AuthenticationError:
    print("Wrong password")
except ConnectionError:
    print("Cannot reach device")
```

## MQTT Bridge

The `MqttBridge` class publishes property changes to MQTT and subscribes to set commands.

```python
from wattpilot_api import Wattpilot, MqttBridge, MqttConfig
from wattpilot_api.api_definition import load_api_definition

api_def = load_api_definition()
config = MqttConfig(host="localhost", port=1883)

async with Wattpilot("192.168.1.100", "password") as wp:
    bridge = MqttBridge(wp, config, api_def)
    await bridge.start()
    # ... bridge publishes property changes to MQTT
    await bridge.stop()
```

## Home Assistant Discovery

```python
from wattpilot_api import HomeAssistantDiscovery, HaConfig

ha = HomeAssistantDiscovery(wp, bridge, HaConfig(enabled=True), api_def)
await ha.discover_all()
await ha.publish_initial_values()
```

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests (100% coverage required)
pytest --cov=wattpilot_api --cov-report=term-missing --cov-fail-under=100

# Run integration tests against a real device
WATTPILOT_HOST=192.168.1.100 WATTPILOT_PASSWORD=password pytest -m integration -v

# Lint and type check
ruff check src/ tests/
mypy src/wattpilot_api/

# Pre-commit (runs ruff, ruff-format, mypy)
pre-commit run --all-files
```

## Project Structure

```
src/wattpilot_api/
├── __init__.py          # Public API exports
├── client.py            # Async WebSocket client
├── auth.py              # PBKDF2 + bcrypt authentication
├── models.py            # Enums and dataclasses
├── exceptions.py        # Exception hierarchy
├── api_definition.py    # YAML property metadata loader
├── mqtt.py              # Async MQTT bridge
├── ha_discovery.py      # Home Assistant MQTT discovery
├── shell.py             # Async CLI shell
├── py.typed             # PEP 561 marker
└── resources/
    └── wattpilot.yaml   # Property definitions (3300+ lines)
```

## API Sources

The WebSocket API has been reverse-engineered from multiple sources:
- [go-eCharger API v1](https://github.com/goecharger/go-eCharger-API-v1/blob/master/go-eCharger%20API%20v1%20EN.md)
- [go-eCharger API v2](https://github.com/goecharger/go-eCharger-API-v2/blob/main/apikeys-en.md)

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history, migration guide, and upstream issue fixes.

## License

MIT License — see [LICENSE](LICENSE) for details.

## Disclaimer

This project uses a reverse-engineered API and is not officially supported by Fronius. Use at your own risk.

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Async Python library for interfacing with the Fronius Wattpilot Wallbox via a reverse-engineered WebSocket API. Provides an async WebSocket client, an interactive CLI shell, an MQTT bridge, and Home Assistant MQTT discovery. Fully typed, 100% test coverage.

## Build & Development Commands

```bash
# Install in development mode (with dev dependencies)
pip install -e ".[dev]"

# Run tests with coverage (must reach 100%)
pytest --cov=wattpilot_api --cov-report=term-missing --cov-fail-under=100

# Run integration tests against a real device
WATTPILOT_HOST=<ip> WATTPILOT_PASSWORD=<pass> pytest -m integration -v

# Run the interactive shell
WATTPILOT_HOST=<ip> WATTPILOT_PASSWORD=<pass> wattpilotshell

# Enable MQTT bridge and Home Assistant discovery
MQTT_ENABLED=true MQTT_HOST=<broker> HA_ENABLED=true wattpilotshell

# Lint
ruff check src/ tests/

# Type check
mypy src/wattpilot_api/
```

## Architecture

### Source Layout

```
src/wattpilot_api/
├── __init__.py          # Public API exports, __version__
├── client.py            # Async Wattpilot WebSocket client
├── auth.py              # Authentication (PBKDF2 + bcrypt)
├── models.py            # Enums (IntEnum), dataclasses
├── exceptions.py        # Exception hierarchy
├── definition.py        # YAML API definition loader
├── mqtt.py              # Async MQTT bridge (aiomqtt)
├── discovery.py         # Home Assistant MQTT discovery
├── shell.py             # Async CLI shell (prompt_toolkit)
├── py.typed             # PEP 561 marker
└── resources/
    └── wattpilot.yaml   # Property metadata (3300+ lines)
```

### Key Modules

- **`client.py`** — `Wattpilot` class: async context manager, WebSocket connection, PBKDF2/bcrypt auth, property synchronization, callbacks (sync + async)
- **`auth.py`** — Password hashing (PBKDF2/bcrypt), auth response computation, HMAC message signing
- **`models.py`** — `LoadMode`, `CarStatus`, `AccessState`, `ErrorState`, `CableLockMode` enums; `MqttConfig`, `HaConfig`, `DeviceInfo` dataclasses
- **`exceptions.py`** — `WattpilotError` → `ConnectionError`, `AuthenticationError`, `PropertyError`, `CommandError`
- **`definition.py`** — Loads `wattpilot.yaml`, validates structure, splits child properties
- **`mqtt.py`** — `MqttBridge` class + value encoding/decoding helpers
- **`discovery.py`** — `HomeAssistantDiscovery` class for MQTT discovery protocol
- **`shell.py`** — `WattpilotShell` async CLI using prompt_toolkit

### WebSocket Message Flow

`hello → authRequired → auth → authSuccess → fullStatus → deltaStatus`

The `Wattpilot` class connects via `websockets`, authenticates (PBKDF2 default, bcrypt for Wattpilot Flex devices), then receives `fullStatus` followed by `deltaStatus` messages. Property changes propagate via registered callbacks.

### Dependencies

- `websockets>=14.0` — async WebSocket client
- `pyyaml>=6.0` — YAML API definition
- `aiomqtt>=2.0` — async MQTT bridge
- `bcrypt>=4.0` — bcrypt authentication
- `prompt-toolkit>=3.0` — async CLI shell

## Key Conventions

- **Python >=3.12** — uses match/case, modern type hints, `type` aliases
- **Fully async** — all IO uses `async`/`await`, compatible with Home Assistant
- **Property keys** are short codes from the go-eCharger API (e.g., `amp`, `alw`, `nrg`, `lmo`)
- **Configuration via environment variables** — prefixed `WATTPILOT_*`, `MQTT_*`, `HA_*`
- **Value mapping** uses `valueMap` dicts in `wattpilot.yaml` to translate numeric ↔ human-readable
- **MQTT topics** use template placeholders: `{baseTopic}`, `{propName}`, `{serialNumber}`, `{component}`, `{uniqueId}`
- **No global mutable state** — all state is in class instances

## Modifying Charger Properties

1. Update `wattpilot.yaml` — add/modify the property entry (key, jsonType, rw, title, description, valueMap, homeAssistant block, childProps)
2. If adding a named property accessor, add a `@property` in `client.py` and update `_update_property()`
3. Include a `homeAssistant` block with `component` and `config` for HA discovery support
4. Add tests — coverage must remain at 100%

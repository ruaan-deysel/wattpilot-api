# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-02-10

Complete async rewrite of the library. This is a **breaking change** from 0.2.x.

### Added
- **Fully async API** using `asyncio` and `websockets>=14.0` — compatible with Home Assistant
- **Async context manager** support: `async with Wattpilot(...) as wp:`
- **bcrypt authentication** for Wattpilot Flex devices (Home FLEX 11 C6, FLEX 22kW, etc.)
  - Automatic detection via `hash` attribute in `authRequired` message
  - Fallback detection via `devicetype: wattpilot_flex` for early Flex firmware
  - bcrypt.js-compatible custom base64 encoding for serial-based salt generation
- **Async MQTT bridge** using `aiomqtt>=2.0` (replaces sync `paho-mqtt`)
- **Async CLI shell** using `prompt_toolkit>=3.0` (replaces sync `cmd2`)
- **Structured exception hierarchy**: `WattpilotError` → `ConnectionError`, `AuthenticationError`, `PropertyError`, `CommandError`
- **Type-safe enums and dataclasses** in `models.py`:
  - `LoadMode`, `CarStatus`, `AccessState`, `ErrorState`, `CableLockMode` (IntEnum)
  - `AuthHashType` (StrEnum)
  - `MqttConfig`, `HaConfig`, `DeviceInfo` (dataclasses)
- **`ApiDefinition` dataclass** with `load_api_definition()` — YAML-driven property metadata as a first-class library feature
- **Full type hints** throughout, verified with `mypy --strict`
- **PEP 561** `py.typed` marker for downstream type checking
- **100% test coverage** — 241 unit tests + 18 integration tests against real hardware
- **Pre-commit hooks** with ruff, ruff-format, mypy, and standard checks
- **PEP 621 packaging** with hatchling build backend
- **Configurable timeouts** for connection and property initialization
- **Sync and async callback support** — property change callbacks can be regular functions or coroutines
- **Graceful error handling** for unknown properties from newer firmware versions

### Changed
- **Package renamed**: `wattpilot` → `wattpilot-api` (import as `wattpilot_api`)
- **Python requirement**: `>=3.10` → `>=3.12`
- **All I/O is async**: `connect()` → `await wp.connect()`, `set_power()` → `await wp.set_power()`
- **Property accessors** use snake_case: `carConnected` → `car_connected`, `AllowCharging` → `allow_charging`, `WifiSSID` → `wifi_ssid`
- **Raw values stored** instead of mapped strings — `wp.error_state` returns `0` (int), not `"Unknown Error"` (str). Use `ErrorState(wp.error_state)` for the enum.
- **No global mutable state** — all state lives in class instances
- **Modular architecture**: 8 focused modules instead of 2 monolithic files
- **Dependencies replaced**:
  - `websocket-client` → `websockets>=14.0`
  - `paho-mqtt` → `aiomqtt>=2.0`
  - `cmd2` → `prompt-toolkit>=3.0`

### Fixed
- **Flex authentication failure** — original library only supported PBKDF2, causing "Wrong password" on all Flex devices ([joscha82/wattpilot#46](https://github.com/joscha82/wattpilot/issues/46))
- **paho-mqtt v2.0 crash** — `mqtt.Client(client_id)` broke in paho-mqtt 2.0 which requires `callback_api_version` ([joscha82/wattpilot#43](https://github.com/joscha82/wattpilot/issues/43))
- **Unknown property crashes** (`'acl'`, `'rfd'`, `'loty'`) — newer firmware sends properties not in the hardcoded value maps, causing `KeyError` and reconnect loops ([joscha82/wattpilot#36](https://github.com/joscha82/wattpilot/issues/36), [joscha82/wattpilot#34](https://github.com/joscha82/wattpilot/issues/34))
- **Process termination after hours** — sync `websocket-client` + threading had no robust reconnection ([joscha82/wattpilot#33](https://github.com/joscha82/wattpilot/issues/33))
- **Cannot reconnect** — calling `connect()` after connection loss raised "socket is already opened" ([joscha82/wattpilot#31](https://github.com/joscha82/wattpilot/issues/31))
- **Child property MQTT publishing** — split properties like `nrg_ptotal` were not updated when listed in `MQTT_PROPERTIES` ([joscha82/wattpilot#28](https://github.com/joscha82/wattpilot/issues/28))
- **MQTT set value type errors** — payloads arrived as strings but device expects integers; proper type conversion based on `jsonType` ([joscha82/wattpilot#23](https://github.com/joscha82/wattpilot/issues/23))
- **Version property** returns `None` — now falls back to the version from the hello message when not present in status data

### Removed
- `setup.py`, `setup.cfg` — replaced by `pyproject.toml`
- `cmd2` dependency — replaced by `prompt-toolkit`
- `websocket-client` dependency — replaced by `websockets`
- `paho-mqtt` dependency — replaced by `aiomqtt`
- Global mutable state (`wp`, `wpdef`, `mqtt_client` module globals)
- Docker/docker-compose files (out of scope for the library)

---

## Migration Guide

### From 0.2.x to 1.0.0

This is a full rewrite. Key changes:

**Package name:**
```python
# Before
from wattpilot import Wattpilot

# After
from wattpilot_api import Wattpilot
```

**Async API:**
```python
# Before (sync + threading)
wp = Wattpilot("192.168.1.100", "password")
wp.connect()
time.sleep(5)
print(wp.amp)

# After (async)
async with Wattpilot("192.168.1.100", "password") as wp:
    print(wp.amp)
    await wp.set_power(16)
```

**Property names (snake_case):**
| Before | After |
|---|---|
| `wp.carConnected` | `wp.car_connected` |
| `wp.AllowCharging` | `wp.allow_charging` |
| `wp.WifiSSID` | `wp.wifi_ssid` |
| `wp.cableType` | `wp.cable_type` |
| `wp.cableLock` | `wp.cable_lock` |
| `wp.errorState` | `wp.error_state` |
| `wp.energyCounterSinceStart` | `wp.energy_counter_since_start` |
| `wp.energyCounterTotal` | `wp.energy_counter_total` |
| `wp.allProps` | `wp.all_properties` |
| `wp.allPropsInitialized` | `wp.properties_initialized` |

**Callbacks:**
```python
# Before
wp.add_event_handler(Event.WP_PROPERTY, callback)

# After
unsub = wp.on_property_change(callback)  # returns unsubscribe function
unsub()  # to remove
```

**Raw values instead of mapped strings:**
```python
# Before
wp.mode  # "Default" (string)

# After
wp.mode  # 3 (int) — use LoadMode(wp.mode) for LoadMode.DEFAULT
```

---

## Pre-1.0 History

### [0.2.x] - 2024

- MQTT bridge, Home Assistant discovery, interactive shell
- Property value mapping, child property support
- bcrypt auth stub (non-functional)

### [0.1.0] - 2022

- Initial reverse-engineered WebSocket API implementation
- PBKDF2 authentication, local LAN connectivity
- Core `Wattpilot` class with threading-based WebSocket

---

## Security

This project implements a reverse-engineered API. Security measures in place:
- Passwords are hashed client-side (PBKDF2 or bcrypt) before transmission
- HMAC-SHA256 signatures protect setValue commands over unsecured connections
- Always use strong, unique passwords for Wattpilot devices

Report security issues privately to the maintainers.

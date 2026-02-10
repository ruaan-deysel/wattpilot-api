# Copilot Instructions — wattpilot-api

## Project Overview

Python library for communicating with Fronius Wattpilot EV chargers via a **reverse-engineered WebSocket API**. The same protocol is used by the official Wattpilot.Solar mobile app. Two main modules:

- **`src/wattpilot/__init__.py`** — `Wattpilot` class: WebSocket client handling connection, authentication (PBKDF2 or bcrypt depending on device type), and real-time property synchronization.
- **`src/wattpilot/wattpilotshell.py`** — CLI shell (`WattpilotShell`, built on `cmd`), MQTT bridge, and Home Assistant MQTT discovery. Also contains the YAML API-definition loader.

## Architecture & Data Flow

1. **API definition** lives in `src/wattpilot/resources/wattpilot.yaml` — a YAML file defining all known charger messages and 100+ properties (key, type, value maps, HA config). This is the single source of truth for property metadata.
2. `wp_read_apidef()` in `wattpilotshell.py` parses the YAML into the global `wpdef` dict with keys `config`, `messages`, `properties`, and `splitProperties`. Compound properties (arrays/objects) are optionally decomposed into child properties via `childProps`.
3. `Wattpilot.__init__()` opens a `websocket-client` `WebSocketApp`. Messages flow: `hello` → `authRequired` → `auth` → `authSuccess` → `fullStatus` (partial batches) → `deltaStatus` (live updates). Each updates `_allProps` dict and typed convenience properties.
4. Property changes propagate via callbacks (`register_property_callback`, `register_message_callback`) used by the MQTT bridge and HA discovery.

## Key Conventions

- **Configuration is entirely via environment variables** (`WATTPILOT_*`, `MQTT_*`, `HA_*`). Defaults are set in `main_setup_env()` at the bottom of `wattpilotshell.py`. Never add config files or argparse — env vars are the pattern.
- **Property keys** are short codes from the charger firmware (e.g. `amp`, `alw`, `nrg`, `lmo`). Readable names come from `title`/`alias` fields in `wattpilot.yaml`.
- **Value mapping**: Many properties use `valueMap` dicts in the YAML to translate numeric API values to human-readable strings (e.g. `lmo: {3: "Default", 4: "Eco", 5: "Next Trip"}`). Encoding/decoding via `mqtt_get_encoded_property()` / `mqtt_get_decoded_property()`.
- **Global mutable state**: `wp`, `wpdef`, `mqtt_client`, and config variables are module-level globals in `wattpilotshell.py`. Be aware of this when modifying functions.
- **Logging**: Uses `logging` module with `_LOGGER = logging.getLogger(__name__)`. Debug level is controlled by `WATTPILOT_DEBUG_LEVEL` env var.

## Build & Run

```bash
# Install in development mode:
pip install -e .

# Run the shell (requires WATTPILOT_HOST and WATTPILOT_PASSWORD env vars):
export WATTPILOT_HOST=<ip>  WATTPILOT_PASSWORD=<pw>
wattpilotshell

# Scripted one-shot command:
wattpilotshell <host> <password> "get amp"
```

- Python >= 3.10 required. Dependencies: `websocket-client`, `PyYAML`, `paho-mqtt`, `cmd2`, `bcrypt`.
- No test suite exists yet. Validate changes manually via the shell against a real or mocked charger.
- Package uses `setuptools` with `src/` layout. Entry point: `wattpilotshell=wattpilot.wattpilotshell:main`.

## Adding / Modifying Charger Properties

1. Add or update the property entry in `src/wattpilot/resources/wattpilot.yaml` following the existing schema (key, jsonType, rw, title, description, valueMap, homeAssistant, childProps).
2. If the property needs a typed convenience accessor on `Wattpilot`, add a `@property` in `__init__.py` and update `__update_property()` to map the key.
3. For Home Assistant discovery, include a `homeAssistant` block with `component` and `config` (device_class, unit_of_measurement, etc.).

## Authentication

Two hash types are supported based on device type:
- **PBKDF2** (default) — `hashlib.pbkdf2_hmac` with serial as salt
- **bcrypt** (Wattpilot Flex) — custom bcrypt.js-compatible base64 encoding in `__bcryptjs_base64_encode()`

Secured connections wrap `setValue` messages in `securedMsg` with an HMAC signature.

## MQTT Topic Patterns

Topics use `{baseTopic}`, `{propName}`, `{serialNumber}` placeholders substituted by `mqtt_subst_topic()`. The `~` prefix expands to `MQTT_TOPIC_PROPERTY_BASE`. Understand this substitution when modifying topic logic.

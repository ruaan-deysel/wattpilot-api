# Wattpilot

> A Python 3 (>= 3.10) module to interact with Fronius Wattpilot wallboxes

`wattpilot` is a robust, type-safe module to interact with Fronius Wattpilot EV chargers using a reverse-engineered WebSocket API. This API is the same one utilized by the official Wattpilot.Solar mobile app.

**Status**: Production-ready with comprehensive error handling, type safety (Pylance verified), and real-time property synchronization.

## Quick Start

### Installation

```bash
pip install wattpilot
```

### Basic Library Usage

```python
from wattpilot import Wattpilot

# Connect to your Wattpilot charger (local LAN)
wp = Wattpilot("192.168.1.100", "your_password")
wp.connect()

# Wait for connection and property initialization
import time
time.sleep(5)

# Access charger properties
print(f"Current amperage: {wp.amp}A")
print(f"Power output: {wp.power:.2f}kW")
print(f"Car connected: {wp.carConnected}")
print(f"Charge status: {wp.AllowCharging}")

# Set charging amperage
wp.set_power(16)  # Set to 16 amperes

# Register callbacks for property changes
def on_property_changed(name, value):
    print(f"Property '{name}' changed to: {value}")

wp.register_property_callback(on_property_changed)

# Keep the connection alive
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass
```

### Interactive Shell

For exploring and testing without writing code:

```bash
export WATTPILOT_HOST=192.168.1.100
export WATTPILOT_PASSWORD=your_password
wattpilotshell
```

## Features

- **Real-time WebSocket Connection**: Bi-directional communication with Wattpilot chargers
- **Type-Safe Implementation**: Full type hints with zero Pylance errors
- **Comprehensive Property Support**: Access to 100+ charger properties
- **Flexible Connection Modes**: Local LAN or Fronius Cloud connectivity
- **MQTT Integration**: Optional MQTT bridge for remote monitoring
- **Home Assistant Discovery**: Auto-discovery via MQTT with entity configuration
- **Interactive Shell**: Command-line tool for testing and diagnostics
- **Docker Ready**: Container support for MQTT bridge deployment

## Requirements

- **Python**: 3.10 or later
- **Network**: Local network access to Fronius Wattpilot charger (default: HTTP on port 80)
- **Optional**: MQTT broker (for MQTT bridge functionality)
- **Optional**: Home Assistant (for entity discovery)

## API Documentation

See [API.md](API.md) for comprehensive documentation of the API implementation.

The API definition has been compiled from multiple sources:
* [go-eCharger-API-v1](https://github.com/goecharger/go-eCharger-API-v1/blob/master/go-eCharger%20API%20v1%20EN.md)
* [go-eCharger-API-v2](https://github.com/goecharger/go-eCharger-API-v2/blob/main/apikeys-en.md)

## Wattpilot Shell

The interactive shell provides an easy way to explore charger properties and test API commands.

### Installation

```bash
# Install the wattpilot module (if not already installed):
pip install .
```

### Basic Usage

```bash
# Set environment variables:
export WATTPILOT_HOST=<charger_ip_address>
export WATTPILOT_PASSWORD=<charger_password>

# Start the interactive shell:
wattpilotshell

# Example output:
wattpilot> help

Documented commands (type help <topic>):
========================================
EOF      exit  ha    info  properties  server  unwatch  watch
connect  get   help  mqtt  rawvalues   set     values
```

The shell supports TAB-completion for commands and property names.
For detailed command documentation, see [ShellCommands.md](ShellCommands.md).

### Script Integration

Pass commands directly to the shell for script automation:

```bash
# Get a property value:
wattpilotshell <charger_ip> <password> "get amp"

# Set a property value:
wattpilotshell <charger_ip> <password> "set amp 16"

# Get available values:
wattpilotshell <charger_ip> <password> "values"
```

## MQTT Bridge Support

Publish charger properties and messages to an MQTT server for remote monitoring and automation.

### Configuration

Enable MQTT support by setting environment variables:

```bash
export MQTT_ENABLED=true
export MQTT_HOST=<mqtt_broker_address>
export WATTPILOT_HOST=<charger_ip_address>
export WATTPILOT_PASSWORD=<charger_password>
wattpilotshell
```

Fine-tune behavior with additional `MQTT_*` environment variables (see table below).

### Testing MQTT Messages

```bash
# Start MQTT broker (if needed):
mosquitto

# Subscribe to all Wattpilot topics in another terminal:
mosquitto_sub -t 'wattpilot/#' -v
```

## Home Assistant MQTT Discovery Support

Automatically discover and create Home Assistant entities using MQTT discovery.

### Setup

1. Ensure the [MQTT Integration](https://www.home-assistant.io/integrations/mqtt/) is configured in Home Assistant
2. Enable both MQTT and Home Assistant discovery:

```bash
export MQTT_ENABLED=true
export HA_ENABLED=true
export MQTT_HOST=<mqtt_broker_address>
export WATTPILOT_HOST=<charger_ip_address>
export WATTPILOT_PASSWORD=<charger_password>
wattpilotshell
```

### Configuration

Fine-tune discovery behavior with `HA_*` environment variables (see table below):
- `HA_PROPERTIES`: Limit which properties are exposed
- `HA_WAIT_INIT_S`: Initial wait time before publishing discovery config
- `HA_WAIT_PROPS_MS`: Wait time per property to ensure HA processes values

### Verification

```bash
# Subscribe to Home Assistant discovery topics:
mosquitto_sub -t 'homeassistant/#' -v
```

Entity configuration is automatically generated from [wattpilot.yaml](src/wattpilot/resources/wattpilot.yaml).

## Docker Support

Run the MQTT bridge with Home Assistant discovery in a Docker container.

### Production Deployment

```bash
# Build the Docker image:
docker-compose build

# Create .env file with configuration:
cat > .env << EOF
HA_ENABLED=true
MQTT_ENABLED=true
MQTT_HOST=<mqtt_broker_address>
WATTPILOT_HOST=<charger_ip_address>
WATTPILOT_PASSWORD=<charger_password>
EOF

# Start the container (recommended for persistent deployment):
docker-compose up -d
```

### Local Development & Diagnostics

```bash
# Create .env file for local testing:
cat > .env << EOF
HA_ENABLED=false
MQTT_ENABLED=false
WATTPILOT_HOST=<charger_ip_address>
WATTPILOT_PASSWORD=<charger_password>
EOF

# Run the interactive shell:
docker-compose run wattpilot shell
```

## Environment Variables

| Environment Variable        | Description                                                                                                                                                                                  | Default Value                                 |
| --------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------- |
| `HA_ENABLED`                | Enable Home Assistant Discovery                                                                                                                                                              | `false`                                       |
| `HA_PROPERTIES`             | Only discover given properties (leave unset for all properties having `homeAssistant` set in [wattpilot.yaml](src/wattpilot/resources/wattpilot.yaml))                                                                               |                                               |
| `HA_TOPIC_CONFIG`           | Topic pattern for HA discovery config                                                                                                                                                        | `homeassistant/{component}/{uniqueId}/config` |
| `HA_WAIT_INIT_S`            | Wait initial number of seconds after starting discovery (in addition to wait time depending on the number of properties). May be increased, if entities in HA are not populated with values. | `5`                                           |
| `HA_WAIT_PROPS_MS`          | Wait milliseconds per property after discovery before publishing property values. May be increased, if entities in HA are not populated with values.                                         | `50`                                          |
| `MQTT_AVAILABLE_PAYLOAD`    | Payload for the availability topic in case the MQTT bridge is online                                                                                                                                                                                | `online`                              |
| `MQTT_CLIENT_ID`            | MQTT client ID                                                                                                                                                                               | `wattpilot2mqtt`                              |
| `MQTT_ENABLED`              | Enable MQTT                                                                                                                                                                                  | `false`                                       |
| `MQTT_HOST`                 | MQTT host to connect to                                                                                                                                                                      |                                               |
| `MQTT_MESSAGES`             | List of space-separated message types to be published to MQTT (leave unset for all messages)                                                                                                 |                                               |
| `MQTT_NOT_AVAILABLE_PAYLOAD` | Payload for the availability topic in case the MQTT bridge is offline (last will message)                                                                                                                                                                               | `offline`                              |
| `MQTT_PORT`                 | Port of the MQTT host to connect to                                                                                                                                                          | `1883`                                        |
| `MQTT_PROPERTIES`           | List of space-separated property names to publish changes for (leave unset for all properties)                                                                                               |                                               |
| `MQTT_PUBLISH_MESSAGES`     | Publish received Wattpilot messages to MQTT                                                                                                                                                  | `false`                                       |
| `MQTT_PUBLISH_PROPERTIES`   | Publish received property values to MQTT                                                                                                                                                     | `true`                                        |
| `MQTT_TOPIC_AVAILABLE`      | Topic pattern to publish Wattpilot availability status to                                                                                                                                               | `{baseTopic}/available`          |
| `MQTT_TOPIC_BASE`           | Base topic for MQTT                                                                                                                                                                          | `wattpilot`                                   |
| `MQTT_TOPIC_MESSAGES`       | Topic pattern to publish Wattpilot messages to                                                                                                                                               | `{baseTopic}/messages/{messageType}`          |
| `MQTT_TOPIC_PROPERTY_BASE`  | Base topic for properties                                                                                                                                                                    | `{baseTopic}/properties/{propName}`           |
| `MQTT_TOPIC_PROPERTY_SET`   | Topic pattern to listen for property value changes for                                                                                                                                       | `~/set`                                       |
| `MQTT_TOPIC_PROPERTY_STATE` | Topic pattern to publish property values to                                                                                                                                                  | `~/state`                                     |
| `WATTPILOT_AUTOCONNECT`     | Automatically connect to Wattpilot on startup                                                                                                                                                | `true`                                        |
| `WATTPILOT_CONNECT_TIMEOUT` | Connect timeout for Wattpilot connection                                                                                                                                                     | `30`                                          |
| `WATTPILOT_DEBUG_LEVEL`     | Debug level                                                                                                                                                                                  | `INFO`                                        |
| `WATTPILOT_HOST`            | IP address of the Wattpilot device to connect to                                                                                                                                             |                                               |
| `WATTPILOT_INIT_TIMEOUT`    | Wait timeout for property initialization                                                                                                                                                     | `30`                                          |
| `WATTPILOT_PASSWORD`        | Password for connecting to the Wattpilot device                                                                                                                                              |                                               |
| `WATTPILOT_SPLIT_PROPERTIES` | Whether compound properties (e.g. JSON arrays or objects) should be decomposed into separate properties                                                                                      | `true`                                        |

## Contributing & API Improvements

The API definition in [wattpilot.yaml](src/wattpilot/resources/wattpilot.yaml) is constantly being improved. Contributions are welcome!

### How to Help

1. Review properties in [wattpilot.yaml](src/wattpilot/resources/wattpilot.yaml)
2. Add missing information to properties you care about:
   - `title`: Human-readable property name
   - `description`: What the property does
   - `rw`: Read/Write permissions (R or RW)
   - `jsonType`: Data type (string, number, boolean, array, object)
   - `childProps`: Child properties for complex types
   - `homeAssistant`: Home Assistant platform configuration
   - `device_class`: HA device class for better UX
   - `unit_of_measurement`: Display unit
   - `enabled_by_default`: Auto-enable in discovery

The file contains extensive examples and documentation to help you get started.

### API Documentation

See [API.md](API.md) for automatically generated documentation of all available properties.

## Troubleshooting

### Connection Issues

- Verify the Wattpilot device is accessible on your local network
- Check that `WATTPILOT_HOST` and `WATTPILOT_PASSWORD` are correctly set
- Increase timeout values if connecting over unstable networks:
  ```bash
  export WATTPILOT_CONNECT_TIMEOUT=60
  export WATTPILOT_INIT_TIMEOUT=60
  ```

### MQTT / Home Assistant Issues

- Ensure the MQTT broker is reachable and authenticated
- Enable debug logging to diagnose problems:
  ```bash
  export WATTPILOT_DEBUG_LEVEL=DEBUG
  wattpilotshell
  ```
- If HA entities don't populate values, increase timing parameters:
  ```bash
  export HA_WAIT_INIT_S=10
  export HA_WAIT_PROPS_MS=100
  ```

## Support & Issues

- **Bug Reports**: [GitHub Issues](https://github.com/joscha82/wattpilot/issues)
- **Discussions**: [GitHub Discussions](https://github.com/joscha82/wattpilot/discussions)
- **Documentation**: [API.md](API.md), [ShellCommands.md](ShellCommands.md)

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history and updates.

## License

MIT License — see [LICENSE](LICENSE) file for details.

Copyright (c) 2022 joscha82

## Disclaimer

This project is a reverse-engineered implementation of the Wattpilot WebSocket API and is not officially supported by Fronius. Use at your own risk. The authors are not responsible for any damages caused by this software.

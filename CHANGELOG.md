# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned
- Full test suite with pytest
- Support for additional Wattpilot device variants
- Prometheus metrics export
- Improved documentation and examples

## [0.2.2] - 2026-02-10

### Added
- **Type Safety**: Full type hints throughout codebase, verified with Pylance
- **Child Property Support**: Decomposition of complex array/object properties into individual entities
- **MQTT Topic Templating**: Flexible topic pattern substitution with placeholders
- **Home Assistant Discovery Enhancements**:
  - Automatic entity component selection (sensor, switch, binary_sensor, number, select)
  - Support for device classes and units of measurement
  - Entity category configuration (config, diagnostic, system)
  - Enable/disable control for discovered entities
- **Docker Support**: docker-compose configuration for MQTT bridge deployment
- **Environment Variable Validation**: Schema validation for wattpilot.yaml on startup
- **Timeout Support**: Configurable connection and initialization timeouts
- **Reconnection Logic**: Automatic MQTT client reconnection with exponential backoff
- **Comprehensive Documentation**:
  - Interactive shell command reference (ShellCommands.md)
  - Full API documentation (API.md)
  - 100+ documented charger properties

### Changed
- **Shell Command Structure**: Refactored `mqtt` and `ha` commands for better organization
- **MQTT Property Publishing**: Split compound properties into individual MQTT topics when `WATTPILOT_SPLIT_PROPERTIES=true`
- **Authentication**: Improved support for both PBKDF2 (default) and bcrypt hash variants
- **Error Handling**: Better error messages and logging throughout

### Fixed
- MQTT disconnection handling and reconnection
- Property callback registration/unregistration
- Unicode encoding for device serials in bcrypt authentication
- Home Assistant entity initialization synchronization

## [0.2.1] - 2024-11-15

### Added
- Basic Home Assistant MQTT discovery
- Property value mapping and encoding/decoding
- Interactive shell with TAB completion
- Watch command for monitoring property/message changes

### Fixed
- WebSocket reconnection handling
- Authentication token validation

## [0.2.0] - 2024-08-20

### Added
- MQTT bridge for property publishing and subscription
- Support for bcrypt authentication (Wattpilot Flex devices)
- Delta status message handling for efficient property updates
- Message callback support
- Property callback support

### Changed
- Restructured WebSocket message handling
- Improved property initialization logic

## [0.1.0] - 2022-09-01

### Added
- Initial reverse-engineered WebSocket API implementation
- Core `Wattpilot` class for connection and control
- PBKDF2 authentication support
- Local LAN connectivity
- Real-time property synchronization
- Basic property accessors (amp, power, voltage, modes, etc.)
- Cloud connectivity support via Fronius API
- Interactive shell with basic commands

---

## Migration Guide

### From 0.1.x to 0.2.x

The public API remains stable. Main improvements are internal:

- **MQTT**: Now requires explicit `MQTT_ENABLED=true` to activate (was auto-enabled)
- **Environment Variables**: New `WATTPILOT_SPLIT_PROPERTIES` controls property decomposition
- **Type Hints**: Full type hints added (no breaking changes to Python <3.10 users needing types)

### From 0.2.1 to 0.2.2

Minor bug fixes and enhancements:
- Home Assistant property names now include parent property reference
- Better timeout handling in initialization
- Improved MQTT reconnection resilience

---

## Versioning

Before v1.0.0, the project uses the following versioning:
- **0.x.y**: Development/alpha releases
- Breaking API changes may occur without notice
- v1.0.0 will mark stability commitment

---

## Contributing

Contributions are welcome! Areas for improvement:
- Test coverage (currently 0%)
- Documentation of internal APIs
- Performance optimization for large property sets
- Support for additional Wattpilot device models

Please see [README.md](README.md) for contribution guidelines.

---

## Security

This project implements a reverse-engineered API. While security measures are in place:
- Passwords are hashed client-side before transmission
- HMAC signatures protect setValue commands over unsecured connections
- Always use strong, unique passwords for Wattpilot devices
- For cloud connectivity, ensure TLS is enabled

Report security issues privately to the maintainers.

"""Enums and dataclasses for Wattpilot property values and configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum, StrEnum


class LoadMode(IntEnum):
    """Charging load mode."""

    DEFAULT = 3
    ECO = 4
    NEXTTRIP = 5


class CarStatus(IntEnum):
    """Car connection / charging status."""

    NO_CAR = 1
    CHARGING = 2
    READY = 3
    COMPLETE = 4


class AccessState(IntEnum):
    """Access / lock state."""

    OPEN = 0
    WAIT = 1


class ErrorState(IntEnum):
    """Device error state."""

    UNKNOWN = 0
    IDLE = 1
    CHARGING = 2
    WAIT_CAR = 3
    COMPLETE = 4
    ERROR = 5


class CableLockMode(IntEnum):
    """Cable lock behaviour."""

    NORMAL = 0
    AUTO_UNLOCK = 1
    ALWAYS_LOCK = 2


class AuthHashType(StrEnum):
    """Authentication hash algorithm."""

    PBKDF2 = "pbkdf2"
    BCRYPT = "bcrypt"


@dataclass(frozen=True, slots=True)
class MqttConfig:
    """MQTT bridge configuration."""

    host: str = ""
    port: int = 1883
    client_id: str = "wattpilot2mqtt"
    topic_base: str = "wattpilot"
    topic_messages: str = "{baseTopic}/messages/{messageType}"
    topic_property_base: str = "{baseTopic}/properties/{propName}"
    topic_property_set: str = "~/set"
    topic_property_state: str = "~/state"
    topic_available: str = "{baseTopic}/available"
    publish_messages: bool = False
    publish_properties: bool = True
    properties: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class HaConfig:
    """Home Assistant discovery configuration."""

    enabled: bool = False
    topic_config: str = "homeassistant/{component}/{uniqueId}/config"
    properties: list[str] = field(default_factory=list)
    disabled_entities: bool = False
    wait_init_s: int = 0
    wait_props_ms: int = 0


@dataclass
class DeviceInfo:
    """Wattpilot device information populated from the hello message."""

    serial: str = ""
    name: str = ""
    hostname: str = ""
    friendly_name: str = ""
    manufacturer: str = ""
    device_type: str = ""
    protocol: int = 0
    secured: int = 0
    version: str = ""
    firmware: str = ""

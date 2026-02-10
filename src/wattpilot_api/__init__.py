"""Async Python library for Fronius Wattpilot Wallbox devices."""

from wattpilot_api.api_definition import ApiDefinition, load_api_definition
from wattpilot_api.client import Wattpilot
from wattpilot_api.exceptions import (
    AuthenticationError,
    CommandError,
    ConnectionError,
    PropertyError,
    WattpilotError,
)
from wattpilot_api.ha_discovery import HomeAssistantDiscovery
from wattpilot_api.models import (
    AccessState,
    CableLockMode,
    CarStatus,
    DeviceInfo,
    ErrorState,
    HaConfig,
    LoadMode,
    MqttConfig,
)
from wattpilot_api.mqtt import MqttBridge

__version__ = "1.0.0"

__all__ = [
    "AccessState",
    "ApiDefinition",
    "AuthenticationError",
    "CableLockMode",
    "CarStatus",
    "CommandError",
    "ConnectionError",
    "DeviceInfo",
    "ErrorState",
    "HaConfig",
    "HomeAssistantDiscovery",
    "LoadMode",
    "MqttBridge",
    "MqttConfig",
    "PropertyError",
    "Wattpilot",
    "WattpilotError",
    "__version__",
    "load_api_definition",
]

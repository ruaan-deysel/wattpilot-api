"""Async Python library for Fronius Wattpilot Wallbox devices."""

from wattpilot_api._version import __version__
from wattpilot_api.client import Wattpilot
from wattpilot_api.definition import ApiDefinition, load_api_definition
from wattpilot_api.discovery import HomeAssistantDiscovery
from wattpilot_api.exceptions import (
    AuthenticationError,
    CommandError,
    ConnectionError,
    PropertyError,
    WattpilotError,
)
from wattpilot_api.models import (
    AccessState,
    CableLockMode,
    CarStatus,
    CloudInfo,
    DeviceInfo,
    ErrorState,
    ForceState,
    HaConfig,
    LoadMode,
    MqttConfig,
    PhaseSwitchMode,
)
from wattpilot_api.mqtt import MqttBridge

__all__ = [
    "AccessState",
    "ApiDefinition",
    "AuthenticationError",
    "CableLockMode",
    "CarStatus",
    "CloudInfo",
    "CommandError",
    "ConnectionError",
    "DeviceInfo",
    "ErrorState",
    "ForceState",
    "HaConfig",
    "HomeAssistantDiscovery",
    "LoadMode",
    "MqttBridge",
    "MqttConfig",
    "PhaseSwitchMode",
    "PropertyError",
    "Wattpilot",
    "WattpilotError",
    "__version__",
    "load_api_definition",
]

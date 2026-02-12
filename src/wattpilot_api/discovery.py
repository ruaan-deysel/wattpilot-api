"""Home Assistant MQTT discovery for Wattpilot properties."""

from __future__ import annotations

import asyncio
import json
import logging
import math
from typing import TYPE_CHECKING, Any

from wattpilot_api.utils import JSONNamespaceEncoder

if TYPE_CHECKING:
    from wattpilot_api.client import Wattpilot
    from wattpilot_api.definition import ApiDefinition
    from wattpilot_api.models import HaConfig
    from wattpilot_api.mqtt import MqttBridge

_LOGGER = logging.getLogger(__name__)


def get_device_info(wp: Wattpilot) -> dict[str, Any]:
    """Build the HA device info dict from a connected Wattpilot instance."""
    device: dict[str, Any] = {
        "connections": [],
        "identifiers": [f"wattpilot_{wp.serial}"],
        "manufacturer": wp.manufacturer,
        "model": wp.device_type,
        "name": wp.name,
        "suggested_area": "Garage",
        "sw_version": wp.version,
    }
    all_props = wp.all_properties
    if "maca" in all_props:
        device["connections"].append(["mac", all_props["maca"]])
    if "macs" in all_props:
        device["connections"].append(["mac", all_props["macs"]])
    return device


def get_component_for_property(pd: dict[str, Any]) -> str:
    """Determine the HA component type for a property definition."""
    component = "sensor"
    rw = pd.get("rw", "")
    json_type = pd.get("jsonType", "")

    if rw == "R/W":
        if "valueMap" in pd:
            component = "select"
        elif json_type == "boolean":
            component = "switch"
        elif json_type in ("float", "integer"):
            component = "number"
    elif rw == "R" and json_type == "boolean":
        component = "binary_sensor"

    return component


def get_default_config(pd: dict[str, Any]) -> dict[str, Any]:
    """Build default HA discovery config for a property."""
    config: dict[str, Any] = {}
    rw = pd.get("rw", "")

    if rw == "R/W":
        if pd.get("jsonType", "") in ("float", "integer"):
            config["mode"] = "box"
        if pd.get("category", "") == "Config":
            config["entity_category"] = "config"

    if "homeAssistant" not in pd:
        config["enabled_by_default"] = False

    return config


class HomeAssistantDiscovery:
    """Manages Home Assistant MQTT discovery for Wattpilot properties."""

    def __init__(
        self,
        wattpilot: Wattpilot,
        mqtt_bridge: MqttBridge,
        config: HaConfig,
        api_def: ApiDefinition,
    ) -> None:
        self._wp = wattpilot
        self._mqtt = mqtt_bridge
        self._config = config
        self._api_def = api_def
        self._properties: list[str] = list(config.properties) if config.properties else []

    @property
    def properties(self) -> list[str]:
        return self._properties

    def _resolve_properties(self) -> list[str]:
        """Resolve which properties to discover."""
        if self._properties:
            return self._properties
        return [p["key"] for p in self._api_def.properties.values() if self._is_default_property(p)]

    def _is_default_property(self, pd: dict[str, Any]) -> bool:
        has_ha = "homeAssistant" in pd
        if not self._config.disabled_entities:
            ha = pd.get("homeAssistant") or {}
            has_ha = has_ha and ha.get("config", {}).get("enabled_by_default", True)
        return has_ha

    async def discover_all(self) -> None:
        """Send discovery configs for all configured properties."""
        self._properties = self._resolve_properties()
        self._mqtt.properties = list(self._properties)
        for name in self._properties:
            await self.discover_property(name)

    async def discover_property(
        self,
        name: str,
        *,
        disable: bool = False,
        force_enablement: bool | None = None,
    ) -> None:
        """Publish HA discovery config for a single property."""
        if self._mqtt._client is None:
            return

        pd = self._api_def.properties.get(name)
        if pd is None:
            _LOGGER.warning("Unknown property '%s' for HA discovery", name)
            return

        ha_info: dict[str, Any] = pd.get("homeAssistant") or {}
        component = ha_info.get("component", get_component_for_property(pd))
        title = pd.get("title", pd.get("alias", name))

        unique_id = f"wattpilot_{self._wp.serial}_{name}"
        object_id = f"wattpilot_{name}"

        from wattpilot_api.mqtt import substitute_topic

        topic_subst = {
            "component": component,
            "propName": name,
            "serialNumber": self._wp.serial,
            "uniqueId": unique_id,
        }

        device_info = get_device_info(self._wp)
        base_topic = substitute_topic(
            self._mqtt._config.topic_property_base,
            topic_subst,
            topic_base=self._mqtt._config.topic_base,
            expand_tilde=False,
        )

        state_topic = substitute_topic(
            self._mqtt._config.topic_property_state,
            topic_subst,
            topic_property_base=self._mqtt._config.topic_property_base,
            topic_base=self._mqtt._config.topic_base,
            expand_tilde=False,
        )

        available_topic = substitute_topic(
            self._mqtt._config.topic_available,
            {},
            topic_base=self._mqtt._config.topic_base,
        )

        discovery_config = get_default_config(pd) | {
            "~": base_topic,
            "name": title,
            "object_id": object_id,
            "unique_id": unique_id,
            "state_topic": state_topic,
            "availability_topic": available_topic,
            "payload_available": "online",
            "payload_not_available": "offline",
            "device": device_info,
        }

        if "valueMap" in pd:
            discovery_config["options"] = list(pd["valueMap"].values())

        if pd.get("rw", "") == "R/W":
            set_topic = substitute_topic(
                self._mqtt._config.topic_property_set,
                topic_subst,
                topic_property_base=self._mqtt._config.topic_property_base,
                topic_base=self._mqtt._config.topic_base,
                expand_tilde=False,
            )
            discovery_config["command_topic"] = set_topic

        # Merge HA-specific config from YAML
        ha_config = ha_info.get("config", {})
        discovery_config = discovery_config | ha_config

        if force_enablement is not None:
            discovery_config["enabled_by_default"] = force_enablement

        config_topic = substitute_topic(
            self._config.topic_config,
            topic_subst,
            topic_base=self._mqtt._config.topic_base,
        )

        payload = "" if disable else json.dumps(discovery_config, cls=JSONNamespaceEncoder)
        await self._mqtt._client.publish(config_topic, payload, retain=True)

        # Publish read-only sensor mirror for R/W properties
        if pd.get("rw", "") == "R/W" and component != "sensor":
            if payload:
                sensor_config = dict(discovery_config)
                sensor_config.pop("command_topic", None)
                payload = json.dumps(sensor_config, cls=JSONNamespaceEncoder)
            sensor_topic = substitute_topic(
                self._config.topic_config,
                topic_subst | {"component": "sensor"},
                topic_base=self._mqtt._config.topic_base,
            )
            await self._mqtt._client.publish(sensor_topic, payload, retain=True)

        # Handle child properties
        if "childProps" in pd:
            for cp in pd["childProps"]:
                await self.discover_property(
                    cp["key"],
                    disable=disable,
                    force_enablement=force_enablement,
                )

    async def undiscover_property(self, name: str) -> None:
        """Remove a property from HA discovery."""
        await self.discover_property(name, disable=True)

    async def publish_initial_values(self) -> None:
        """Publish current values for all discovered properties."""
        for name in self._properties:
            all_props = self._wp.all_properties
            if name in all_props:
                pd = self._api_def.properties[name]
                await self._mqtt.publish_property(pd, all_props[name])

    async def stop(self) -> None:
        """Undiscover all properties."""
        for name in list(self._properties):
            await self.undiscover_property(name)

    async def setup(self) -> None:
        """Full HA setup: discover properties, wait, publish initial values."""
        await self.discover_all()

        wait_time = math.ceil(
            self._config.wait_init_s + len(self._properties) * self._config.wait_props_ms * 0.001
        )
        if wait_time > 0:
            _LOGGER.info("Waiting %ds for HA to discover entities...", wait_time)
            await asyncio.sleep(wait_time)

        await self.publish_initial_values()

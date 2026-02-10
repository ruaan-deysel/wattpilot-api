"""Tests for Home Assistant MQTT discovery."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from wattpilot_api.api_definition import ApiDefinition
from wattpilot_api.ha_discovery import (
    HomeAssistantDiscovery,
    _JSONNamespaceEncoder,
    get_component_for_property,
    get_default_config,
    get_device_info,
)
from wattpilot_api.models import HaConfig, MqttConfig
from wattpilot_api.mqtt import MqttBridge


def _make_mock_wp() -> MagicMock:
    wp = MagicMock()
    wp.serial = "12345678"
    wp.manufacturer = "fronius"
    wp.device_type = "wattpilot"
    wp.name = "My WP"
    wp.version = "36.3"
    wp.all_properties = {"amp": 16, "lmo": 3}
    wp.on_property_change = MagicMock(return_value=MagicMock())
    wp.set_property = AsyncMock()
    return wp


def _make_mqtt_config() -> MqttConfig:
    return MqttConfig(
        host="localhost",
        port=1883,
        client_id="test",
        topic_base="wattpilot",
        topic_property_base="{baseTopic}/properties/{propName}",
        topic_property_set="~/set",
        topic_property_state="~/state",
        topic_available="{baseTopic}/available",
    )


def _make_api_def() -> ApiDefinition:
    return ApiDefinition(
        properties={
            "amp": {
                "key": "amp",
                "jsonType": "integer",
                "rw": "R/W",
                "title": "Ampere",
                "homeAssistant": {"component": "number", "config": {}},
            },
            "lmo": {
                "key": "lmo",
                "jsonType": "integer",
                "rw": "R/W",
                "title": "Load Mode",
                "homeAssistant": {"component": "select", "config": {}},
                "valueMap": {"3": "Default", "4": "Eco"},
            },
            "car": {
                "key": "car",
                "jsonType": "integer",
                "rw": "R",
                "title": "Car Status",
                "homeAssistant": {"component": "sensor", "config": {}},
            },
            "fhz": {"key": "fhz", "jsonType": "float", "rw": "R", "title": "Frequency"},
        }
    )


def _make_bridge(wp: MagicMock, api_def: ApiDefinition | None = None) -> MqttBridge:
    config = _make_mqtt_config()
    bridge = MqttBridge(wp, config, api_def or _make_api_def())
    bridge._client = MagicMock()
    bridge._client.publish = AsyncMock()
    return bridge


class TestJSONNamespaceEncoder:
    def test_simple_namespace(self) -> None:
        from types import SimpleNamespace

        ns = SimpleNamespace(x=1)
        result = json.dumps(ns, cls=_JSONNamespaceEncoder)
        assert '"x": 1' in result

    def test_fallback(self) -> None:
        with pytest.raises(TypeError):
            json.dumps(object(), cls=_JSONNamespaceEncoder)


class TestGetDeviceInfo:
    def test_basic_info(self) -> None:
        wp = _make_mock_wp()
        wp.all_properties = {}
        info = get_device_info(wp)
        assert info["identifiers"] == ["wattpilot_12345678"]
        assert info["manufacturer"] == "fronius"
        assert info["model"] == "wattpilot"
        assert info["name"] == "My WP"
        assert info["sw_version"] == "36.3"

    def test_mac_addresses(self) -> None:
        wp = _make_mock_wp()
        wp.all_properties = {"maca": "aa:bb:cc:dd:ee:ff", "macs": "11:22:33:44:55:66"}
        info = get_device_info(wp)
        assert ["mac", "aa:bb:cc:dd:ee:ff"] in info["connections"]
        assert ["mac", "11:22:33:44:55:66"] in info["connections"]

    def test_no_mac(self) -> None:
        wp = _make_mock_wp()
        wp.all_properties = {}
        info = get_device_info(wp)
        assert info["connections"] == []


class TestGetComponentForProperty:
    def test_read_only_sensor(self) -> None:
        pd: dict[str, Any] = {"key": "amp", "rw": "R", "jsonType": "integer"}
        assert get_component_for_property(pd) == "sensor"

    def test_rw_with_value_map(self) -> None:
        pd: dict[str, Any] = {"key": "lmo", "rw": "R/W", "valueMap": {"3": "Default"}}
        assert get_component_for_property(pd) == "select"

    def test_rw_boolean(self) -> None:
        pd: dict[str, Any] = {"key": "alw", "rw": "R/W", "jsonType": "boolean"}
        assert get_component_for_property(pd) == "switch"

    def test_rw_number(self) -> None:
        pd: dict[str, Any] = {"key": "amp", "rw": "R/W", "jsonType": "integer"}
        assert get_component_for_property(pd) == "number"

    def test_rw_float(self) -> None:
        pd: dict[str, Any] = {"key": "x", "rw": "R/W", "jsonType": "float"}
        assert get_component_for_property(pd) == "number"

    def test_read_only_boolean(self) -> None:
        pd: dict[str, Any] = {"key": "x", "rw": "R", "jsonType": "boolean"}
        assert get_component_for_property(pd) == "binary_sensor"

    def test_no_rw(self) -> None:
        pd: dict[str, Any] = {"key": "x", "jsonType": "integer"}
        assert get_component_for_property(pd) == "sensor"


class TestGetDefaultConfig:
    def test_rw_number(self) -> None:
        pd: dict[str, Any] = {"key": "amp", "rw": "R/W", "jsonType": "integer"}
        config = get_default_config(pd)
        assert config["mode"] == "box"

    def test_rw_config_category(self) -> None:
        pd: dict[str, Any] = {"key": "x", "rw": "R/W", "jsonType": "integer", "category": "Config"}
        config = get_default_config(pd)
        assert config["entity_category"] == "config"

    def test_no_ha_block(self) -> None:
        pd: dict[str, Any] = {"key": "x", "rw": "R"}
        config = get_default_config(pd)
        assert config["enabled_by_default"] is False

    def test_with_ha_block(self) -> None:
        pd: dict[str, Any] = {"key": "x", "rw": "R", "homeAssistant": {"component": "sensor"}}
        config = get_default_config(pd)
        assert "enabled_by_default" not in config

    def test_rw_float(self) -> None:
        pd: dict[str, Any] = {"key": "x", "rw": "R/W", "jsonType": "float"}
        config = get_default_config(pd)
        assert config["mode"] == "box"

    def test_readonly(self) -> None:
        pd: dict[str, Any] = {"key": "x", "rw": "R", "jsonType": "integer"}
        config = get_default_config(pd)
        assert "mode" not in config


class TestHomeAssistantDiscoveryInit:
    def test_init(self) -> None:
        wp = _make_mock_wp()
        bridge = _make_bridge(wp)
        ha_config = HaConfig()
        ha = HomeAssistantDiscovery(wp, bridge, ha_config, _make_api_def())
        assert ha.properties == []

    def test_init_with_properties(self) -> None:
        wp = _make_mock_wp()
        bridge = _make_bridge(wp)
        ha_config = HaConfig(properties=["amp", "lmo"])
        ha = HomeAssistantDiscovery(wp, bridge, ha_config, _make_api_def())
        assert ha.properties == ["amp", "lmo"]


class TestHomeAssistantDiscoverProperty:
    async def test_discover_rw_property(self) -> None:
        wp = _make_mock_wp()
        bridge = _make_bridge(wp)
        ha_config = HaConfig()
        ha = HomeAssistantDiscovery(wp, bridge, ha_config, _make_api_def())

        await ha.discover_property("amp")
        # Should publish config and sensor mirror (R/W gets both)
        assert bridge._client.publish.call_count == 2

    async def test_discover_ro_property(self) -> None:
        wp = _make_mock_wp()
        bridge = _make_bridge(wp)
        ha_config = HaConfig()
        ha = HomeAssistantDiscovery(wp, bridge, ha_config, _make_api_def())

        await ha.discover_property("car")
        # Read-only: just the config
        assert bridge._client.publish.call_count == 1

    async def test_discover_with_value_map(self) -> None:
        wp = _make_mock_wp()
        bridge = _make_bridge(wp)
        ha_config = HaConfig()
        ha = HomeAssistantDiscovery(wp, bridge, ha_config, _make_api_def())

        await ha.discover_property("lmo")
        call_args = bridge._client.publish.call_args_list[0]
        payload = json.loads(call_args[0][1])
        assert "options" in payload
        assert "Default" in payload["options"]

    async def test_undiscover_property(self) -> None:
        wp = _make_mock_wp()
        bridge = _make_bridge(wp)
        ha_config = HaConfig()
        ha = HomeAssistantDiscovery(wp, bridge, ha_config, _make_api_def())

        await ha.undiscover_property("amp")
        # Should publish empty payload
        call_args = bridge._client.publish.call_args_list[0]
        assert call_args[0][1] == ""

    async def test_discover_force_enablement(self) -> None:
        wp = _make_mock_wp()
        bridge = _make_bridge(wp)
        ha_config = HaConfig()
        ha = HomeAssistantDiscovery(wp, bridge, ha_config, _make_api_def())

        await ha.discover_property("amp", force_enablement=True)
        call_args = bridge._client.publish.call_args_list[0]
        payload = json.loads(call_args[0][1])
        assert payload["enabled_by_default"] is True

    async def test_discover_force_disable(self) -> None:
        wp = _make_mock_wp()
        bridge = _make_bridge(wp)
        ha_config = HaConfig()
        ha = HomeAssistantDiscovery(wp, bridge, ha_config, _make_api_def())

        await ha.discover_property("amp", force_enablement=False)
        call_args = bridge._client.publish.call_args_list[0]
        payload = json.loads(call_args[0][1])
        assert payload["enabled_by_default"] is False

    async def test_discover_unknown_property(self) -> None:
        wp = _make_mock_wp()
        bridge = _make_bridge(wp)
        ha_config = HaConfig()
        ha = HomeAssistantDiscovery(wp, bridge, ha_config, _make_api_def())

        await ha.discover_property("unknown")
        bridge._client.publish.assert_not_called()

    async def test_discover_no_client(self) -> None:
        wp = _make_mock_wp()
        bridge = _make_bridge(wp)
        bridge._client = None
        ha_config = HaConfig()
        ha = HomeAssistantDiscovery(wp, bridge, ha_config, _make_api_def())

        await ha.discover_property("amp")  # Should not raise

    async def test_discover_with_child_props(self) -> None:
        wp = _make_mock_wp()
        api_def = ApiDefinition(
            properties={
                "nrg": {
                    "key": "nrg",
                    "jsonType": "array",
                    "rw": "R",
                    "title": "Energy",
                    "homeAssistant": {"component": "sensor", "config": {}},
                    "childProps": [
                        {
                            "key": "nrg_v1",
                            "jsonType": "integer",
                            "rw": "R",
                            "title": "V1",
                            "homeAssistant": {"component": "sensor", "config": {}},
                        },
                    ],
                },
                "nrg_v1": {
                    "key": "nrg_v1",
                    "jsonType": "integer",
                    "rw": "R",
                    "title": "V1",
                    "parentProperty": "nrg",
                    "valueRef": "0",
                    "homeAssistant": {"component": "sensor", "config": {}},
                },
            }
        )
        bridge = _make_bridge(wp, api_def)
        ha_config = HaConfig()
        ha = HomeAssistantDiscovery(wp, bridge, ha_config, api_def)

        await ha.discover_property("nrg")
        assert bridge._client.publish.call_count == 2  # parent + child


class TestHomeAssistantDiscoverAll:
    async def test_discover_all_default(self) -> None:
        wp = _make_mock_wp()
        bridge = _make_bridge(wp)
        ha_config = HaConfig()
        ha = HomeAssistantDiscovery(wp, bridge, ha_config, _make_api_def())

        await ha.discover_all()
        # Should discover amp, lmo, car (all have homeAssistant blocks)
        assert len(ha.properties) == 3
        assert bridge._client.publish.call_count > 0

    async def test_discover_all_disabled_entities(self) -> None:
        wp = _make_mock_wp()
        bridge = _make_bridge(wp)
        ha_config = HaConfig(disabled_entities=True)
        ha = HomeAssistantDiscovery(wp, bridge, ha_config, _make_api_def())

        await ha.discover_all()
        # With disabled_entities=True, all HA properties should be included
        assert len(ha.properties) >= 3

    async def test_discover_all_with_explicit_properties(self) -> None:
        wp = _make_mock_wp()
        bridge = _make_bridge(wp)
        ha_config = HaConfig(properties=["amp"])
        ha = HomeAssistantDiscovery(wp, bridge, ha_config, _make_api_def())

        await ha.discover_all()
        assert ha.properties == ["amp"]


class TestHomeAssistantPublishInitial:
    async def test_publish_initial_values(self) -> None:
        wp = _make_mock_wp()
        wp.all_properties = {"amp": 16, "lmo": 3}
        bridge = _make_bridge(wp)
        ha_config = HaConfig()
        ha = HomeAssistantDiscovery(wp, bridge, ha_config, _make_api_def())
        ha._properties = ["amp", "lmo"]

        await ha.publish_initial_values()
        assert bridge._client.publish.call_count == 2

    async def test_publish_initial_missing_prop(self) -> None:
        wp = _make_mock_wp()
        wp.all_properties = {"amp": 16}
        bridge = _make_bridge(wp)
        ha_config = HaConfig()
        ha = HomeAssistantDiscovery(wp, bridge, ha_config, _make_api_def())
        ha._properties = ["amp", "missing"]

        await ha.publish_initial_values()
        # Only amp should be published
        assert bridge._client.publish.call_count == 1


class TestHomeAssistantStop:
    async def test_stop(self) -> None:
        wp = _make_mock_wp()
        bridge = _make_bridge(wp)
        ha_config = HaConfig()
        ha = HomeAssistantDiscovery(wp, bridge, ha_config, _make_api_def())
        ha._properties = ["amp"]

        await ha.stop()
        # Should undiscover (empty payload)
        assert bridge._client.publish.call_count > 0


class TestHomeAssistantSetup:
    async def test_setup(self) -> None:
        wp = _make_mock_wp()
        bridge = _make_bridge(wp)
        ha_config = HaConfig(wait_init_s=0, wait_props_ms=0)
        ha = HomeAssistantDiscovery(wp, bridge, ha_config, _make_api_def())

        await ha.setup()
        assert len(ha.properties) > 0
        assert bridge._client.publish.call_count > 0

    async def test_setup_with_wait(self) -> None:
        wp = _make_mock_wp()
        bridge = _make_bridge(wp)
        # Very small wait to keep tests fast
        ha_config = HaConfig(wait_init_s=0, wait_props_ms=1)
        ha = HomeAssistantDiscovery(wp, bridge, ha_config, _make_api_def())

        await ha.setup()
        assert len(ha.properties) > 0


class TestIsDefaultProperty:
    def test_with_ha_enabled(self) -> None:
        wp = _make_mock_wp()
        bridge = _make_bridge(wp)
        ha_config = HaConfig(disabled_entities=False)
        ha = HomeAssistantDiscovery(wp, bridge, ha_config, _make_api_def())
        # Property with homeAssistant and enabled_by_default not explicitly False
        assert ha._is_default_property({"key": "amp", "homeAssistant": {"config": {}}}) is True

    def test_without_ha(self) -> None:
        wp = _make_mock_wp()
        bridge = _make_bridge(wp)
        ha_config = HaConfig(disabled_entities=False)
        ha = HomeAssistantDiscovery(wp, bridge, ha_config, _make_api_def())
        assert ha._is_default_property({"key": "x"}) is False

    def test_with_disabled_entities_true(self) -> None:
        wp = _make_mock_wp()
        bridge = _make_bridge(wp)
        ha_config = HaConfig(disabled_entities=True)
        ha = HomeAssistantDiscovery(wp, bridge, ha_config, _make_api_def())
        prop_def = {
            "key": "amp",
            "homeAssistant": {
                "config": {"enabled_by_default": False},
            },
        }
        assert ha._is_default_property(prop_def) is True

    def test_explicitly_disabled(self) -> None:
        wp = _make_mock_wp()
        bridge = _make_bridge(wp)
        ha_config = HaConfig(disabled_entities=False)
        ha = HomeAssistantDiscovery(wp, bridge, ha_config, _make_api_def())
        prop_def = {
            "key": "amp",
            "homeAssistant": {
                "config": {"enabled_by_default": False},
            },
        }
        assert ha._is_default_property(prop_def) is False

    def test_ha_none_config(self) -> None:
        wp = _make_mock_wp()
        bridge = _make_bridge(wp)
        ha_config = HaConfig(disabled_entities=False)
        ha = HomeAssistantDiscovery(wp, bridge, ha_config, _make_api_def())
        # homeAssistant key present but None
        assert ha._is_default_property({"key": "amp", "homeAssistant": None}) is True

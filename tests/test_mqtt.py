"""Tests for the MQTT bridge helpers and MqttBridge class."""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wattpilot_api.definition import ApiDefinition
from wattpilot_api.models import MqttConfig
from wattpilot_api.mqtt import (
    MqttBridge,
    _JSONNamespaceEncoder,
    decode_property,
    encode_property,
    map_property,
    map_value,
    remap_property,
    remap_value,
    substitute_topic,
)


class TestJSONNamespaceEncoder:
    def test_simple_namespace(self) -> None:
        from types import SimpleNamespace

        ns = SimpleNamespace(a=1, b="two")
        result = json.dumps(ns, cls=_JSONNamespaceEncoder)
        assert '"a": 1' in result
        assert '"b": "two"' in result

    def test_regular_object_fallback(self) -> None:
        with pytest.raises(TypeError):
            json.dumps(object(), cls=_JSONNamespaceEncoder)


class TestMapValue:
    def test_no_value_map(self) -> None:
        pd: dict[str, Any] = {"key": "amp"}
        assert map_value(pd, 16) == 16

    def test_with_value_map(self) -> None:
        pd: dict[str, Any] = {"key": "lmo", "valueMap": {"3": "Default", "4": "Eco"}}
        assert map_value(pd, 3) == "Default"
        assert map_value(pd, 4) == "Eco"

    def test_none_value(self) -> None:
        pd: dict[str, Any] = {"key": "amp", "valueMap": {"1": "one"}}
        assert map_value(pd, None) is None

    def test_unmapped_value(self) -> None:
        pd: dict[str, Any] = {"key": "lmo", "valueMap": {"3": "Default"}}
        assert map_value(pd, 99) == 99


class TestMapProperty:
    def test_scalar(self) -> None:
        pd: dict[str, Any] = {"key": "lmo", "valueMap": {"3": "Default"}}
        assert map_property(pd, 3) == "Default"

    def test_array(self) -> None:
        pd: dict[str, Any] = {
            "key": "arr",
            "jsonType": "array",
            "valueMap": {"1": "on", "0": "off"},
        }
        result = map_property(pd, [1, 0, 1])
        assert result == ["on", "off", "on"]

    def test_none(self) -> None:
        pd: dict[str, Any] = {"key": "x"}
        assert map_property(pd, None) is None


class TestRemapValue:
    def test_no_value_map(self) -> None:
        pd: dict[str, Any] = {"key": "amp"}
        assert remap_value(pd, 16) == 16

    def test_with_value_map(self) -> None:
        pd: dict[str, Any] = {"key": "lmo", "valueMap": {"3": "Default", "4": "Eco"}}
        assert remap_value(pd, "Default") == 3
        assert remap_value(pd, "Eco") == 4

    def test_unmapped_value(self) -> None:
        pd: dict[str, Any] = {"key": "lmo", "valueMap": {"3": "Default"}}
        assert remap_value(pd, "Unknown") == "Unknown"


class TestRemapProperty:
    def test_scalar(self) -> None:
        pd: dict[str, Any] = {"key": "lmo", "valueMap": {"3": "Default"}}
        assert remap_property(pd, "Default") == 3

    def test_array(self) -> None:
        pd: dict[str, Any] = {
            "key": "arr",
            "jsonType": "array",
            "valueMap": {"1": "on", "0": "off"},
        }
        result = remap_property(pd, ["on", "off"])
        assert result == [1, 0]


class TestEncodeProperty:
    def test_integer(self) -> None:
        pd: dict[str, Any] = {"key": "amp", "jsonType": "integer"}
        assert encode_property(pd, 16) == 16

    def test_boolean(self) -> None:
        pd: dict[str, Any] = {"key": "alw", "jsonType": "boolean"}
        assert encode_property(pd, True) == "true"

    def test_array(self) -> None:
        pd: dict[str, Any] = {"key": "nrg", "jsonType": "array"}
        result = encode_property(pd, [1, 2, 3])
        assert result == "[1, 2, 3]"

    def test_object(self) -> None:
        pd: dict[str, Any] = {"key": "obj", "jsonType": "object"}
        result = encode_property(pd, {"a": 1})
        assert '"a"' in result

    def test_none(self) -> None:
        pd: dict[str, Any] = {"key": "x", "jsonType": "integer"}
        assert encode_property(pd, None) == "null"

    def test_with_value_map(self) -> None:
        pd: dict[str, Any] = {"key": "lmo", "jsonType": "integer", "valueMap": {"3": "Default"}}
        assert encode_property(pd, 3) == "Default"

    def test_string_type(self) -> None:
        pd: dict[str, Any] = {"key": "wss", "jsonType": "string"}
        assert encode_property(pd, "MyWiFi") == "MyWiFi"


class TestDecodeProperty:
    def test_integer(self) -> None:
        pd: dict[str, Any] = {"key": "amp", "jsonType": "integer"}
        assert decode_property(pd, 16) == 16

    def test_array(self) -> None:
        pd: dict[str, Any] = {"key": "nrg", "jsonType": "array"}
        result = decode_property(pd, "[1, 2, 3]")
        assert result == [1, 2, 3]

    def test_object(self) -> None:
        pd: dict[str, Any] = {"key": "obj", "jsonType": "object"}
        result = decode_property(pd, '{"a": 1}')
        assert result == {"a": 1}

    def test_with_value_map(self) -> None:
        pd: dict[str, Any] = {"key": "lmo", "jsonType": "integer", "valueMap": {"3": "Default"}}
        assert decode_property(pd, "Default") == 3

    def test_integer_string(self) -> None:
        pd: dict[str, Any] = {"key": "amp", "jsonType": "integer"}
        assert decode_property(pd, "42") == 42

    def test_float_string(self) -> None:
        pd: dict[str, Any] = {"key": "fhz", "jsonType": "float"}
        assert decode_property(pd, "50.5") == 50.5

    def test_boolean_true(self) -> None:
        pd: dict[str, Any] = {"key": "alw", "jsonType": "boolean"}
        assert decode_property(pd, "true") is True

    def test_boolean_false(self) -> None:
        pd: dict[str, Any] = {"key": "alw", "jsonType": "boolean"}
        assert decode_property(pd, "false") is False

    def test_string_type(self) -> None:
        pd: dict[str, Any] = {"key": "wss", "jsonType": "string"}
        assert decode_property(pd, "hello") == "hello"


class TestSubstituteTopic:
    def test_basic_substitution(self) -> None:
        result = substitute_topic(
            "{baseTopic}/properties/{propName}",
            {"propName": "amp"},
            topic_base="wattpilot",
        )
        assert result == "wattpilot/properties/amp"

    def test_tilde_expansion(self) -> None:
        result = substitute_topic(
            "~/set",
            {"propName": "amp"},
            topic_property_base="{baseTopic}/properties/{propName}",
            topic_base="wattpilot",
        )
        assert result == "wattpilot/properties/amp/set"

    def test_no_tilde_expansion(self) -> None:
        result = substitute_topic(
            "~/set",
            {},
            topic_property_base="base",
            expand_tilde=False,
        )
        assert result == "~/set"

    def test_multiple_placeholders(self) -> None:
        result = substitute_topic(
            "{baseTopic}/{serialNumber}/{propName}",
            {"serialNumber": "123", "propName": "amp"},
            topic_base="wp",
        )
        assert result == "wp/123/amp"


def _make_mock_wp() -> MagicMock:
    wp = MagicMock()
    wp.serial = "12345678"
    wp.all_properties = {"amp": 16, "lmo": 3}
    wp.on_property_change = MagicMock(return_value=MagicMock())
    wp.set_property = AsyncMock()
    return wp


def _make_config(**kwargs: Any) -> MqttConfig:
    defaults = {
        "host": "localhost",
        "port": 1883,
        "client_id": "test",
        "topic_base": "wattpilot",
        "topic_property_base": "{baseTopic}/properties/{propName}",
        "topic_property_set": "~/set",
        "topic_property_state": "~/state",
        "topic_available": "{baseTopic}/available",
    }
    return MqttConfig(**(defaults | kwargs))


def _make_api_def() -> ApiDefinition:
    return ApiDefinition(
        properties={
            "amp": {"key": "amp", "jsonType": "integer", "rw": "R/W"},
            "lmo": {"key": "lmo", "jsonType": "integer", "rw": "R/W", "valueMap": {"3": "Default"}},
            "car": {"key": "car", "jsonType": "integer", "rw": "R"},
        }
    )


class TestMqttBridgeInit:
    def test_init(self) -> None:
        wp = _make_mock_wp()
        config = _make_config()
        api_def = _make_api_def()
        bridge = MqttBridge(wp, config, api_def)
        assert bridge.properties == []

    def test_init_with_properties(self) -> None:
        wp = _make_mock_wp()
        config = _make_config(properties=["amp", "lmo"])
        api_def = _make_api_def()
        bridge = MqttBridge(wp, config, api_def)
        assert bridge.properties == ["amp", "lmo"]

    def test_properties_setter(self) -> None:
        wp = _make_mock_wp()
        bridge = MqttBridge(wp, _make_config(), _make_api_def())
        bridge.properties = ["amp"]
        assert bridge.properties == ["amp"]


class TestMqttBridgePublish:
    async def test_publish_property(self) -> None:
        wp = _make_mock_wp()
        bridge = MqttBridge(wp, _make_config(), _make_api_def())
        bridge._client = MagicMock()
        bridge._client.publish = AsyncMock()
        bridge._properties = ["amp"]

        await bridge.publish_property({"key": "amp", "jsonType": "integer"}, 16)
        bridge._client.publish.assert_called_once()
        call_args = bridge._client.publish.call_args
        assert "amp" in call_args[0][0]

    async def test_publish_property_no_client(self) -> None:
        wp = _make_mock_wp()
        bridge = MqttBridge(wp, _make_config(), _make_api_def())
        bridge._client = None
        # Should not raise
        await bridge.publish_property({"key": "amp", "jsonType": "integer"}, 16)

    async def test_publish_property_not_in_list(self) -> None:
        wp = _make_mock_wp()
        bridge = MqttBridge(wp, _make_config(), _make_api_def())
        bridge._client = MagicMock()
        bridge._client.publish = AsyncMock()
        bridge._properties = ["lmo"]

        await bridge.publish_property({"key": "amp", "jsonType": "integer"}, 16)
        bridge._client.publish.assert_not_called()

    async def test_publish_property_forced(self) -> None:
        wp = _make_mock_wp()
        bridge = MqttBridge(wp, _make_config(), _make_api_def())
        bridge._client = MagicMock()
        bridge._client.publish = AsyncMock()
        bridge._properties = ["lmo"]

        await bridge.publish_property({"key": "amp", "jsonType": "integer"}, 16, force=True)
        bridge._client.publish.assert_called_once()

    async def test_publish_with_child_props(self) -> None:
        wp = _make_mock_wp()
        wp.all_properties = {"nrg": [230, 231, 232]}
        api_def = ApiDefinition(
            properties={
                "nrg": {"key": "nrg", "jsonType": "array"},
                "nrg_v1": {
                    "key": "nrg_v1",
                    "parentProperty": "nrg",
                    "valueRef": "0",
                    "jsonType": "integer",
                },
            }
        )
        bridge = MqttBridge(wp, _make_config(), api_def)
        bridge._client = MagicMock()
        bridge._client.publish = AsyncMock()
        bridge._properties = ["nrg"]

        pd = {
            "key": "nrg",
            "jsonType": "array",
            "childProps": [
                {"key": "nrg_v1", "parentProperty": "nrg", "valueRef": "0", "jsonType": "integer"}
            ],
        }
        await bridge.publish_property(pd, [230, 231, 232])
        assert bridge._client.publish.call_count == 2


class TestMqttBridgeStartStop:
    @patch("wattpilot_api.mqtt.aiomqtt.Client")
    async def test_start(self, mock_client_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.publish = AsyncMock()
        mock_client.subscribe = AsyncMock()
        mock_client.messages = self._make_async_iter([])
        mock_client_cls.return_value = mock_client

        wp = _make_mock_wp()
        bridge = MqttBridge(wp, _make_config(), _make_api_def())
        await bridge.start()

        assert bridge._client is not None
        mock_client.publish.assert_called_once()
        mock_client.subscribe.assert_called_once()
        wp.on_property_change.assert_called_once()

        # Clean up
        bridge._listen_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await bridge._listen_task

    async def test_stop_with_client(self) -> None:
        wp = _make_mock_wp()
        bridge = MqttBridge(wp, _make_config(), _make_api_def())
        bridge._client = MagicMock()
        bridge._client.publish = AsyncMock()
        bridge._client.__aexit__ = AsyncMock()
        bridge._unsubscribe_props = MagicMock()
        bridge._listen_task = asyncio.create_task(asyncio.sleep(100))

        await bridge.stop()
        assert bridge._client is None
        assert bridge._listen_task is None
        assert bridge._unsubscribe_props is None

    async def test_stop_no_client(self) -> None:
        wp = _make_mock_wp()
        bridge = MqttBridge(wp, _make_config(), _make_api_def())
        await bridge.stop()  # Should not raise

    @staticmethod
    def _make_async_iter(items: list[Any]) -> Any:
        class _AsyncIter:
            def __init__(self, data: list[Any]) -> None:
                self._data = iter(data)

            def __aiter__(self) -> _AsyncIter:
                return self

            async def __anext__(self) -> Any:
                try:
                    return next(self._data)
                except StopIteration:
                    raise StopAsyncIteration from None

        return _AsyncIter(items)


class TestMqttBridgeOnPropertyChange:
    def test_on_property_change_unknown(self) -> None:
        wp = _make_mock_wp()
        bridge = MqttBridge(wp, _make_config(), _make_api_def())
        bridge._client = MagicMock()
        bridge._client.publish = AsyncMock()

        # Unknown property should not raise
        bridge._on_property_change("unknown_prop", 42)

    async def test_on_property_change_known(self) -> None:
        wp = _make_mock_wp()
        bridge = MqttBridge(wp, _make_config(), _make_api_def())
        bridge._client = MagicMock()
        bridge._client.publish = AsyncMock()

        # Should schedule publish (needs running event loop for ensure_future)
        bridge._on_property_change("amp", 16)
        await asyncio.sleep(0)  # let the scheduled coroutine run


class TestMqttBridgeOnMqttMessage:
    async def test_set_value(self) -> None:
        wp = _make_mock_wp()
        bridge = MqttBridge(wp, _make_config(), _make_api_def())

        msg = MagicMock()
        msg.topic = "wattpilot/properties/amp/set"
        msg.payload = b"10"

        await bridge._on_mqtt_message(msg)
        wp.set_property.assert_called_once_with("amp", 10)

    async def test_set_value_readonly(self) -> None:
        wp = _make_mock_wp()
        bridge = MqttBridge(wp, _make_config(), _make_api_def())

        msg = MagicMock()
        msg.topic = "wattpilot/properties/car/set"
        msg.payload = b"1"

        await bridge._on_mqtt_message(msg)
        wp.set_property.assert_not_called()

    async def test_set_value_unknown_prop(self) -> None:
        wp = _make_mock_wp()
        bridge = MqttBridge(wp, _make_config(), _make_api_def())

        msg = MagicMock()
        msg.topic = "wattpilot/properties/unknown/set"
        msg.payload = b"1"

        await bridge._on_mqtt_message(msg)
        wp.set_property.assert_not_called()

    async def test_non_matching_topic(self) -> None:
        wp = _make_mock_wp()
        bridge = MqttBridge(wp, _make_config(), _make_api_def())

        msg = MagicMock()
        msg.topic = "other/topic"
        msg.payload = b"1"

        await bridge._on_mqtt_message(msg)
        wp.set_property.assert_not_called()

    async def test_set_value_bytes_payload(self) -> None:
        wp = _make_mock_wp()
        bridge = MqttBridge(wp, _make_config(), _make_api_def())

        msg = MagicMock()
        msg.topic = "wattpilot/properties/amp/set"
        msg.payload = b"16"

        await bridge._on_mqtt_message(msg)
        wp.set_property.assert_called_once()

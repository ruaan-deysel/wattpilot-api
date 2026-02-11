"""Async MQTT bridge for publishing Wattpilot properties."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import aiomqtt

from wattpilot_api.definition import ApiDefinition, get_child_property_value

if TYPE_CHECKING:
    from wattpilot_api.client import Wattpilot
    from wattpilot_api.models import MqttConfig

_LOGGER = logging.getLogger(__name__)


class _JSONNamespaceEncoder(json.JSONEncoder):
    def default(self, o: object) -> Any:
        if isinstance(o, SimpleNamespace):
            return o.__dict__
        return super().default(o)


# ---- Value encoding / decoding helpers ----


def map_value(pd: dict[str, Any], value: Any) -> Any:
    """Apply a forward value-map (numeric -> human-readable)."""
    if value is None:
        return None
    if "valueMap" in pd:
        key = str(value)
        if key in pd["valueMap"]:
            return pd["valueMap"][key]
        _LOGGER.warning(
            "Unable to map value '%s' of property '%s' - using unmapped value!",
            value,
            pd["key"],
        )
    return value


def map_property(pd: dict[str, Any], value: Any) -> Any:
    """Map a complete property value (scalar or array)."""
    if value and "jsonType" in pd and pd["jsonType"] == "array":
        return [map_value(pd, v) for v in value]
    return map_value(pd, value)


def remap_value(pd: dict[str, Any], mapped_value: Any) -> Any:
    """Reverse value-map (human-readable -> numeric)."""
    if "valueMap" not in pd:
        return mapped_value
    vm = pd["valueMap"]
    if mapped_value in vm.values():
        raw_key = list(vm.keys())[list(vm.values()).index(mapped_value)]
        return json.loads(str(raw_key))
    _LOGGER.warning(
        "Unable to remap value '%s' of property '%s' - using mapped value!",
        mapped_value,
        pd["key"],
    )
    return mapped_value


def remap_property(pd: dict[str, Any], mapped_value: Any) -> Any:
    """Reverse-map a complete property value (scalar or array)."""
    if "jsonType" in pd and pd["jsonType"] == "array":
        return [remap_value(pd, v) for v in mapped_value]
    return remap_value(pd, mapped_value)


def encode_property(pd: dict[str, Any], value: Any) -> Any:
    """Encode a property value for MQTT publication (with value mapping)."""
    mapped = map_property(pd, value)
    if value is None or ("jsonType" in pd and pd["jsonType"] in ("array", "object", "boolean")):
        return json.dumps(mapped, cls=_JSONNamespaceEncoder)
    return mapped


def decode_property(pd: dict[str, Any], value: Any) -> Any:
    """Decode a property value received from MQTT (reverse mapping)."""
    json_type = pd.get("jsonType", "")
    decoded = json.loads(value) if json_type in ("array", "object") else value
    remapped = remap_property(pd, decoded)
    # Type-convert string values that were not remapped by a valueMap
    if isinstance(remapped, str):
        if json_type == "integer":
            return int(remapped)
        if json_type == "float":
            return float(remapped)
        if json_type == "boolean":
            return remapped.lower() == "true"
    return remapped


def substitute_topic(
    template: str,
    values: dict[str, str],
    *,
    topic_property_base: str = "",
    topic_base: str = "",
    expand_tilde: bool = True,
) -> str:
    """Substitute ``{placeholders}`` in an MQTT topic template."""
    s = template
    if expand_tilde:
        s = re.sub(r"^~", topic_property_base, s)
    all_values = {"baseTopic": topic_base} | values
    return s.format(**all_values)


class MqttBridge:
    """Async MQTT bridge that publishes Wattpilot property changes."""

    def __init__(
        self,
        wattpilot: Wattpilot,
        config: MqttConfig,
        api_def: ApiDefinition,
    ) -> None:
        self._wp = wattpilot
        self._config = config
        self._api_def = api_def
        self._client: aiomqtt.Client | None = None
        self._unsubscribe_props: Any = None
        self._unsubscribe_msgs: Any = None
        self._listen_task: asyncio.Task[None] | None = None
        self._properties: list[str] = list(config.properties) if config.properties else []

    @property
    def properties(self) -> list[str]:
        return self._properties

    @properties.setter
    def properties(self, value: list[str]) -> None:
        self._properties = value

    async def start(self) -> None:
        """Connect to the MQTT broker and start publishing."""
        self._client = aiomqtt.Client(
            hostname=self._config.host,
            port=self._config.port,
            identifier=self._config.client_id,
        )
        await self._client.__aenter__()

        # Publish availability
        available_topic = self._subst(self._config.topic_available, {})
        await self._client.publish(available_topic, payload="online", qos=0, retain=True)

        # Subscribe to set commands
        set_topic = self._subst(
            self._config.topic_property_set,
            {"propName": "+"},
        )
        await self._client.subscribe(set_topic)

        # Determine which properties to publish
        if not self._properties:
            self._properties = list(self._wp.all_properties.keys())

        # Register property callback
        self._unsubscribe_props = self._wp.on_property_change(self._on_property_change)

        # Start listening for MQTT messages
        self._listen_task = asyncio.create_task(self._listen_loop())

    async def stop(self) -> None:
        """Disconnect from the MQTT broker."""
        if self._listen_task is not None:
            self._listen_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._listen_task
            self._listen_task = None

        if self._unsubscribe_props is not None:
            self._unsubscribe_props()
            self._unsubscribe_props = None

        if self._client is not None:
            available_topic = self._subst(self._config.topic_available, {})
            await self._client.publish(available_topic, payload="offline", qos=0, retain=True)
            await self._client.__aexit__(None, None, None)
            self._client = None

    async def publish_property(
        self,
        pd: dict[str, Any],
        value: Any,
        *,
        force: bool = False,
    ) -> None:
        """Publish a single property value to MQTT."""
        if self._client is None:
            return

        prop_name = pd["key"]
        if not (force or not self._properties or prop_name in self._properties):
            return

        topic = self._subst(
            self._config.topic_property_state,
            {"propName": prop_name, "serialNumber": self._wp.serial},
        )
        encoded = encode_property(pd, value)
        await self._client.publish(topic, str(encoded), retain=True)

        # Publish child properties
        if "childProps" in pd:
            for cpd in pd["childProps"]:
                child_value = get_child_property_value(
                    self._api_def, self._wp.all_properties, cpd["key"]
                )
                await self.publish_property(cpd, child_value, force=True)

    def _on_property_change(self, name: str, value: Any) -> None:
        """Sync callback — schedules async publish."""
        pd = self._api_def.properties.get(name)
        if pd is None:
            return
        task = asyncio.ensure_future(self.publish_property(pd, value))
        task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)

    async def _listen_loop(self) -> None:  # pragma: no cover
        """Listen for incoming MQTT set-value commands."""
        assert self._client is not None
        async for message in self._client.messages:
            await self._on_mqtt_message(message)

    async def _on_mqtt_message(self, message: aiomqtt.Message) -> None:
        """Handle an incoming MQTT message (property set command)."""
        set_pattern = self._subst(
            self._config.topic_property_set,
            {"propName": "([^/]+)"},
        )
        match = re.match(set_pattern, str(message.topic))
        if not match:
            return

        name = match.group(1)
        pd = self._api_def.properties.get(name)
        if pd is None:
            _LOGGER.warning("Unknown property '%s' in MQTT set command", name)
            return
        if pd.get("rw", "R") == "R":
            _LOGGER.warning("Property '%s' is not writable", name)
            return

        raw_payload = message.payload
        payload_str = (
            raw_payload.decode("utf-8") if isinstance(raw_payload, bytes) else str(raw_payload)
        )
        value = decode_property(pd, payload_str)
        _LOGGER.info("MQTT set command: %s = %s", name, value)
        await self._wp.set_property(name, value)

    def _subst(self, template: str, extra: dict[str, str]) -> str:
        return substitute_topic(
            template,
            extra,
            topic_property_base=self._config.topic_property_base,
            topic_base=self._config.topic_base,
        )

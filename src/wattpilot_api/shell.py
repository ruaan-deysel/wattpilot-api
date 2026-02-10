"""Async interactive CLI shell for Wattpilot using prompt_toolkit."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
from types import SimpleNamespace
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.patch_stdout import patch_stdout

from wattpilot_api import __version__
from wattpilot_api.api_definition import (
    ApiDefinition,
    get_all_properties,
    get_child_property_value,
    load_api_definition,
)
from wattpilot_api.client import Wattpilot
from wattpilot_api.ha_discovery import HomeAssistantDiscovery
from wattpilot_api.models import HaConfig, MqttConfig
from wattpilot_api.mqtt import MqttBridge, decode_property, encode_property

_LOGGER = logging.getLogger(__name__)


class _JSONNamespaceEncoder(json.JSONEncoder):
    def default(self, o: object) -> Any:
        if isinstance(o, SimpleNamespace):
            return o.__dict__
        return super().default(o)


def _value_to_json(value: Any) -> str:
    return json.dumps(value, cls=_JSONNamespaceEncoder)


def _env_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


class WattpilotShell:
    """Async interactive shell for Wattpilot."""

    def __init__(
        self,
        api_def: ApiDefinition,
        mqtt_config: MqttConfig,
        ha_config: HaConfig,
        host: str,
        password: str,
        *,
        connect_timeout: int = 30,
        init_timeout: int = 30,
        autoconnect: bool = True,
        split_properties: bool = True,
    ) -> None:
        self._api_def = api_def
        self._mqtt_config = mqtt_config
        self._ha_config = ha_config
        self._host = host
        self._password = password
        self._connect_timeout = connect_timeout
        self._init_timeout = init_timeout
        self._autoconnect = autoconnect
        self._split_properties = split_properties

        self._wp: Wattpilot | None = None
        self._mqtt: MqttBridge | None = None
        self._ha: HomeAssistantDiscovery | None = None

        self._watching_messages: list[str] = []
        self._watching_properties: list[str] = []

        # Build command list for completion
        self._commands = [
            "connect",
            "disconnect",
            "exit",
            "get",
            "ha",
            "help",
            "info",
            "mqtt",
            "properties",
            "rawvalues",
            "server",
            "set",
            "unwatch",
            "values",
            "watch",
        ]

    def _ensure_connected(self) -> bool:
        if self._wp is None or not self._wp.connected:
            print("Not connected to wattpilot!")
            return False
        return True

    def _get_all_props(self, *, available_only: bool = True) -> dict[str, Any]:
        if self._wp is None:
            return {}
        return get_all_properties(
            self._api_def, self._wp.all_properties, available_only=available_only
        )

    def _get_props_matching_regex(self, arg: str, *, available_only: bool = True) -> dict[str, Any]:
        args = arg.split(" ")
        prop_regex = args[0] if args and args[0] else ".*"
        props = {
            k: v
            for k, v in self._get_all_props(available_only=available_only).items()
            if re.match(r"^" + prop_regex + "$", k, flags=re.IGNORECASE)
        }
        value_regex = args[1] if len(args) > 1 else ".*"
        props = {
            k: v
            for k, v in props.items()
            if re.match(
                r"^" + value_regex + "$",
                str(encode_property(self._api_def.properties[k], v)),
                flags=re.IGNORECASE,
            )
        }
        return props

    async def _cmd_connect(self, arg: str) -> None:
        self._wp = Wattpilot(
            self._host,
            self._password,
            connect_timeout=float(self._connect_timeout),
            init_timeout=float(self._init_timeout),
        )
        await self._wp.connect()
        print(f"Connected to {self._wp.name} ({self._wp.serial})")

    async def _cmd_disconnect(self, arg: str) -> None:
        if self._wp:
            await self._wp.disconnect()
            self._wp = None
            print("Disconnected.")

    async def _cmd_info(self, arg: str) -> None:
        if not self._ensure_connected():
            return
        print(self._wp)

    async def _cmd_get(self, arg: str) -> None:
        if not self._ensure_connected():
            return
        assert self._wp is not None
        args = arg.split(" ")
        if not args or args[0] == "":
            print("ERROR: Wrong number of arguments!")
            return
        name = args[0]
        if name in self._wp.all_properties:
            pd = self._api_def.properties[name]
            print(encode_property(pd, self._wp.all_properties[name]))
        elif name in self._api_def.split_properties:
            pd = self._api_def.properties[name]
            print(
                encode_property(
                    pd, get_child_property_value(self._api_def, self._wp.all_properties, name)
                )
            )
        else:
            print(f"ERROR: Unknown property: {name}")

    async def _cmd_set(self, arg: str) -> None:
        if not self._ensure_connected():
            return
        assert self._wp is not None
        args = arg.split(" ")
        if len(args) < 2 or arg == "":
            print("ERROR: Wrong number of arguments!")
            return
        name, raw_value = args[0], args[1]
        if name not in self._wp.all_properties:
            print(f"ERROR: Unknown property: {name}")
            return

        if raw_value.lower() in ("false", "true"):
            v: Any = json.loads(raw_value.lower())
        elif raw_value.isnumeric():
            v = int(raw_value)
        elif raw_value.replace(".", "", 1).isnumeric():
            v = float(raw_value)
        else:
            v = raw_value

        pd = self._api_def.properties[name]
        await self._wp.set_property(name, decode_property(pd, v))

    async def _cmd_properties(self, arg: str) -> None:
        if not self._ensure_connected():
            return
        assert self._wp is not None
        props = self._get_props_matching_regex(arg, available_only=False)
        if not props:
            print("No matching properties found!")
            return
        print("Properties:")
        for name, value in sorted(props.items()):
            pd = self._api_def.properties[name]
            title = pd.get("title", pd.get("alias", name))
            rw = f", rw:{pd['rw']}" if "rw" in pd else ""
            alias = f", alias:{pd['alias']}" if "alias" in pd else ""
            jtype = pd.get("jsonType", "unknown")
            print(f"- {name} ({jtype}{alias}{rw}): {title}")
            if "description" in pd:
                print(f"  Description: {pd['description']}")
            if name in self._wp.all_properties:
                enc = encode_property(pd, value)
                raw = f" (raw:{_value_to_json(value)})" if "valueMap" in pd else ""
                print(f"  Value: {enc}{raw}")
            else:
                print("  NOTE: Not provided by the connected device!")
        print()

    async def _cmd_values(self, arg: str) -> None:
        if not self._ensure_connected():
            return
        print("List values of properties (with value mapping):")
        for name, value in sorted(self._get_props_matching_regex(arg).items()):
            pd = self._api_def.properties[name]
            print(f"- {name}: {encode_property(pd, value)}")
        print()

    async def _cmd_rawvalues(self, arg: str) -> None:
        if not self._ensure_connected():
            return
        print("List raw values of properties (without value mapping):")
        for name, value in sorted(self._get_props_matching_regex(arg).items()):
            print(f"- {name}: {_value_to_json(value)}")
        print()

    async def _cmd_watch(self, arg: str) -> None:
        if not self._ensure_connected():
            return
        assert self._wp is not None
        args = arg.split(" ")
        if len(args) < 2 or arg == "":
            print("ERROR: Wrong number of arguments!")
            return
        kind, target = args[0], args[1]
        if kind == "property":
            if target not in self._wp.all_properties:
                print(f"ERROR: Unknown property: {target}")
                return
            if not self._watching_properties:
                self._wp.on_property_change(self._watched_property_changed)
            if target not in self._watching_properties:
                self._watching_properties.append(target)
        elif kind == "message":
            if target not in self._api_def.messages:
                print(f"ERROR: Unknown message type: {target}")
                return
            if not self._watching_messages:
                self._wp.on_message(self._watched_message_received)
            if target not in self._watching_messages:
                self._watching_messages.append(target)
        else:
            print(f"ERROR: Unknown watch type: {kind}")

    async def _cmd_unwatch(self, arg: str) -> None:
        if not self._ensure_connected():
            return
        args = arg.split(" ")
        if len(args) < 2 or arg == "":
            print("ERROR: Wrong number of arguments!")
            return
        kind, target = args[0], args[1]
        if kind == "property" and target in self._watching_properties:
            self._watching_properties.remove(target)
        elif kind == "message" and target in self._watching_messages:
            self._watching_messages.remove(target)
        else:
            print(f"ERROR: Not watching {kind} '{target}'")

    async def _cmd_mqtt(self, arg: str) -> None:
        if not self._ensure_connected():
            return
        assert self._wp is not None
        args = arg.split(" ")
        if not args or args[0] == "":
            print("ERROR: Wrong number of arguments!")
            return
        subcmd = args[0]
        if subcmd == "start":
            self._mqtt = MqttBridge(self._wp, self._mqtt_config, self._api_def)
            await self._mqtt.start()
            print("MQTT bridge started.")
        elif subcmd == "stop":
            if self._mqtt:
                await self._mqtt.stop()
                self._mqtt = None
            print("MQTT bridge stopped.")
        elif subcmd == "status":
            print(f"MQTT bridge is {'running' if self._mqtt else 'stopped'}.")
        elif subcmd == "properties":
            props = self._mqtt.properties if self._mqtt else []
            print(f"MQTT properties: {props}")
        else:
            print(f"ERROR: Unknown MQTT subcommand: {subcmd}")

    async def _cmd_ha(self, arg: str) -> None:
        if not self._ensure_connected():
            return
        assert self._wp is not None
        args = arg.split(" ")
        if not args or args[0] == "":
            print("ERROR: Wrong number of arguments!")
            return
        subcmd = args[0]
        if subcmd == "start":
            if self._mqtt is None:
                self._mqtt = MqttBridge(self._wp, self._mqtt_config, self._api_def)
                await self._mqtt.start()
            self._ha = HomeAssistantDiscovery(self._wp, self._mqtt, self._ha_config, self._api_def)
            await self._ha.setup()
            print("HA discovery started.")
        elif subcmd == "stop":
            if self._ha:
                await self._ha.stop()
                self._ha = None
            if self._mqtt:
                await self._mqtt.stop()
                self._mqtt = None
            print("HA discovery stopped.")
        elif subcmd == "status":
            print(f"HA discovery is {'running' if self._ha else 'stopped'}.")
        elif subcmd == "properties":
            props = self._ha.properties if self._ha else []
            print(f"HA properties: {props}")
        elif subcmd in ("discover", "undiscover", "enable", "disable") and len(args) > 1:
            prop_name = args[1]
            if self._ha is None:
                print("ERROR: HA discovery not started!")
                return
            if subcmd == "discover":
                await self._ha.discover_property(prop_name, force_enablement=True)
            elif subcmd == "undiscover":
                await self._ha.undiscover_property(prop_name)
            elif subcmd == "enable":
                await self._ha.discover_property(prop_name, force_enablement=True)
            elif subcmd == "disable":
                await self._ha.discover_property(prop_name, force_enablement=False)
        else:
            print(f"ERROR: Unknown HA subcommand: {subcmd}")

    async def _cmd_server(self, arg: str) -> None:
        if not self._ensure_connected():
            return
        _LOGGER.info("Server started.")
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            _LOGGER.info("Server shutting down.")

    async def _cmd_help(self, arg: str) -> None:
        print(f"Wattpilot Shell v{__version__}")
        print("Commands:")
        print("  connect         Connect to Wattpilot")
        print("  disconnect      Disconnect from Wattpilot")
        print("  get <prop>      Get property value")
        print("  set <prop> <v>  Set property value")
        print("  info            Print device info")
        print("  properties [r]  List properties (optional regex filter)")
        print("  values [r] [v]  List values with mapping (optional filters)")
        print("  rawvalues [r]   List raw values (optional regex filter)")
        print("  watch <type> <n>  Watch message/property changes")
        print("  unwatch <type> <n> Unwatch message/property changes")
        print("  mqtt <sub>      MQTT bridge (start|stop|status|properties)")
        print("  ha <sub>        HA discovery (start|stop|status|properties|discover|undiscover)")
        print("  server          Start in server mode")
        print("  exit            Exit the shell")

    def _watched_property_changed(self, name: str, value: Any) -> None:
        if name in self._watching_properties:
            pd = self._api_def.properties.get(name, {})
            print(f"\n[watch] Property {name} changed to {encode_property(pd, value)}")

    def _watched_message_received(self, msg: dict[str, Any]) -> None:
        msg_type = msg.get("type", "")
        if msg_type in self._watching_messages:
            print(f"\n[watch] Message {msg_type}: {json.dumps(msg)}")

    async def run_command(self, line: str) -> bool:
        """Execute a single command. Returns True if the shell should exit."""
        line = line.strip()
        if not line:
            return False

        parts = line.split(" ", 1)
        cmd = parts[0]
        arg = parts[1] if len(parts) > 1 else ""

        handlers: dict[str, Any] = {
            "connect": self._cmd_connect,
            "disconnect": self._cmd_disconnect,
            "exit": None,
            "get": self._cmd_get,
            "ha": self._cmd_ha,
            "help": self._cmd_help,
            "info": self._cmd_info,
            "mqtt": self._cmd_mqtt,
            "properties": self._cmd_properties,
            "rawvalues": self._cmd_rawvalues,
            "server": self._cmd_server,
            "set": self._cmd_set,
            "unwatch": self._cmd_unwatch,
            "values": self._cmd_values,
            "watch": self._cmd_watch,
        }

        if cmd == "exit":
            return True
        if cmd in handlers and handlers[cmd] is not None:
            try:
                await handlers[cmd](arg)
            except Exception as e:
                print(f"ERROR: {e}")
        else:
            print(f"Unknown command: {cmd}. Type 'help' for a list.")
        return False

    async def run(self) -> None:
        """Run the interactive shell loop."""
        print(f"Welcome to the Wattpilot Shell v{__version__}. Type help or ? to list commands.\n")

        if self._autoconnect:
            _LOGGER.info("Automatically connecting to Wattpilot...")
            await self.run_command("connect")
            if self._mqtt_config.host and self._ha_config.enabled:
                await self.run_command("ha start")
            elif self._mqtt_config.host:
                await self.run_command("mqtt start")
            await self.run_command("info")

        completer = WordCompleter(self._commands, ignore_case=True)
        session: PromptSession[str] = PromptSession(completer=completer)

        while True:
            try:
                with patch_stdout():
                    line = await session.prompt_async("wattpilot> ")
                if await self.run_command(line):
                    break
            except (EOFError, KeyboardInterrupt):
                break

        if self._ha:
            await self._ha.stop()
        if self._mqtt:
            await self._mqtt.stop()
        if self._wp:
            await self._wp.disconnect()


def _load_config_from_env() -> dict[str, Any]:
    """Load all configuration from environment variables."""
    host = os.environ.get("WATTPILOT_HOST", "")
    password = os.environ.get("WATTPILOT_PASSWORD", "")
    if not host:
        print("ERROR: WATTPILOT_HOST not set!", file=sys.stderr)
        sys.exit(1)
    if not password:
        print("ERROR: WATTPILOT_PASSWORD not set!", file=sys.stderr)
        sys.exit(1)

    mqtt_enabled = _env_bool(os.environ.get("MQTT_ENABLED"))
    mqtt_host = os.environ.get("MQTT_HOST", "")

    mqtt_config = MqttConfig(
        host=mqtt_host if mqtt_enabled else "",
        port=int(os.environ.get("MQTT_PORT", "1883")),
        client_id=os.environ.get("MQTT_CLIENT_ID", "wattpilot2mqtt"),
        topic_base=os.environ.get("MQTT_TOPIC_BASE", "wattpilot"),
        topic_messages=os.environ.get("MQTT_TOPIC_MESSAGES", "{baseTopic}/messages/{messageType}"),
        topic_property_base=os.environ.get(
            "MQTT_TOPIC_PROPERTY_BASE", "{baseTopic}/properties/{propName}"
        ),
        topic_property_set=os.environ.get("MQTT_TOPIC_PROPERTY_SET", "~/set"),
        topic_property_state=os.environ.get("MQTT_TOPIC_PROPERTY_STATE", "~/state"),
        topic_available=os.environ.get("MQTT_TOPIC_AVAILABLE", "{baseTopic}/available"),
        publish_messages=_env_bool(os.environ.get("MQTT_PUBLISH_MESSAGES")),
        publish_properties=_env_bool(os.environ.get("MQTT_PUBLISH_PROPERTIES", "true"), True),
        properties=os.environ.get("MQTT_PROPERTIES", "").split(),
        messages=os.environ.get("MQTT_MESSAGES", "").split(),
    )

    ha_config = HaConfig(
        enabled=_env_bool(os.environ.get("HA_ENABLED")),
        topic_config=os.environ.get(
            "HA_TOPIC_CONFIG", "homeassistant/{component}/{uniqueId}/config"
        ),
        properties=os.environ.get("HA_PROPERTIES", "").split(),
        disabled_entities=_env_bool(os.environ.get("HA_DISABLED_ENTITIES")),
        wait_init_s=int(os.environ.get("HA_WAIT_INIT_S", "0")),
        wait_props_ms=int(os.environ.get("HA_WAIT_PROPS_MS", "0")),
    )

    return {
        "host": host,
        "password": password,
        "mqtt_config": mqtt_config,
        "ha_config": ha_config,
        "connect_timeout": int(os.environ.get("WATTPILOT_CONNECT_TIMEOUT", "30")),
        "init_timeout": int(os.environ.get("WATTPILOT_INIT_TIMEOUT", "30")),
        "autoconnect": _env_bool(os.environ.get("WATTPILOT_AUTOCONNECT", "true"), True),
        "split_properties": _env_bool(os.environ.get("WATTPILOT_SPLIT_PROPERTIES", "true"), True),
        "debug_level": os.environ.get("WATTPILOT_DEBUG_LEVEL", "INFO"),
    }


def main() -> None:  # pragma: no cover
    """Entry point for the ``wattpilotshell`` CLI command."""
    config = _load_config_from_env()

    # Configure logging
    level_name = str(config["debug_level"]).upper()
    level = getattr(logging, level_name, logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    if not any(isinstance(h, logging.StreamHandler) for h in root_logger.handlers):
        handler = logging.StreamHandler()
        handler.setLevel(level)
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)

    api_def = load_api_definition(split_properties=config["split_properties"])

    shell = WattpilotShell(
        api_def=api_def,
        mqtt_config=config["mqtt_config"],
        ha_config=config["ha_config"],
        host=config["host"],
        password=config["password"],
        connect_timeout=config["connect_timeout"],
        init_timeout=config["init_timeout"],
        autoconnect=config["autoconnect"],
        split_properties=config["split_properties"],
    )

    # Handle single-command mode
    if len(sys.argv) > 1:
        asyncio.run(shell.run_command(" ".join(sys.argv[1:])))
    else:
        asyncio.run(shell.run())

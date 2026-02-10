"""Tests for the async CLI shell."""

from __future__ import annotations

from wattpilot_api.api_definition import ApiDefinition
from wattpilot_api.models import HaConfig, MqttConfig
from wattpilot_api.shell import WattpilotShell, _env_bool


class TestEnvBool:
    def test_none(self) -> None:
        assert _env_bool(None) is False
        assert _env_bool(None, True) is True

    def test_truthy(self) -> None:
        for val in ("1", "true", "True", "TRUE", "yes", "YES", "on", "ON"):
            assert _env_bool(val) is True

    def test_falsy(self) -> None:
        for val in ("0", "false", "False", "no", "off", "", "random"):
            assert _env_bool(val) is False


class TestWattpilotShellInit:
    def test_init(self) -> None:
        api_def = ApiDefinition()
        mqtt_config = MqttConfig()
        ha_config = HaConfig()
        shell = WattpilotShell(
            api_def=api_def,
            mqtt_config=mqtt_config,
            ha_config=ha_config,
            host="192.168.1.1",
            password="test",
        )
        assert shell._host == "192.168.1.1"
        assert shell._wp is None

    def test_ensure_connected_false(self) -> None:
        shell = WattpilotShell(
            api_def=ApiDefinition(),
            mqtt_config=MqttConfig(),
            ha_config=HaConfig(),
            host="x",
            password="x",
        )
        assert shell._ensure_connected() is False


class TestWattpilotShellCommands:
    async def test_help_command(self) -> None:
        shell = WattpilotShell(
            api_def=ApiDefinition(),
            mqtt_config=MqttConfig(),
            ha_config=HaConfig(),
            host="x",
            password="x",
        )
        result = await shell.run_command("help")
        assert result is False

    async def test_exit_command(self) -> None:
        shell = WattpilotShell(
            api_def=ApiDefinition(),
            mqtt_config=MqttConfig(),
            ha_config=HaConfig(),
            host="x",
            password="x",
        )
        result = await shell.run_command("exit")
        assert result is True

    async def test_unknown_command(self) -> None:
        shell = WattpilotShell(
            api_def=ApiDefinition(),
            mqtt_config=MqttConfig(),
            ha_config=HaConfig(),
            host="x",
            password="x",
        )
        result = await shell.run_command("nonsense")
        assert result is False

    async def test_empty_command(self) -> None:
        shell = WattpilotShell(
            api_def=ApiDefinition(),
            mqtt_config=MqttConfig(),
            ha_config=HaConfig(),
            host="x",
            password="x",
        )
        result = await shell.run_command("")
        assert result is False

    async def test_get_not_connected(self) -> None:
        shell = WattpilotShell(
            api_def=ApiDefinition(),
            mqtt_config=MqttConfig(),
            ha_config=HaConfig(),
            host="x",
            password="x",
        )
        result = await shell.run_command("get amp")
        assert result is False

    async def test_set_not_connected(self) -> None:
        shell = WattpilotShell(
            api_def=ApiDefinition(),
            mqtt_config=MqttConfig(),
            ha_config=HaConfig(),
            host="x",
            password="x",
        )
        result = await shell.run_command("set amp 16")
        assert result is False

    async def test_info_not_connected(self) -> None:
        shell = WattpilotShell(
            api_def=ApiDefinition(),
            mqtt_config=MqttConfig(),
            ha_config=HaConfig(),
            host="x",
            password="x",
        )
        result = await shell.run_command("info")
        assert result is False

    async def test_properties_not_connected(self) -> None:
        shell = WattpilotShell(
            api_def=ApiDefinition(),
            mqtt_config=MqttConfig(),
            ha_config=HaConfig(),
            host="x",
            password="x",
        )
        result = await shell.run_command("properties")
        assert result is False

    async def test_mqtt_not_connected(self) -> None:
        shell = WattpilotShell(
            api_def=ApiDefinition(),
            mqtt_config=MqttConfig(),
            ha_config=HaConfig(),
            host="x",
            password="x",
        )
        result = await shell.run_command("mqtt start")
        assert result is False

    async def test_ha_not_connected(self) -> None:
        shell = WattpilotShell(
            api_def=ApiDefinition(),
            mqtt_config=MqttConfig(),
            ha_config=HaConfig(),
            host="x",
            password="x",
        )
        result = await shell.run_command("ha start")
        assert result is False

"""Tests for the async Wattpilot client."""

from __future__ import annotations

import asyncio
import datetime
import json
from types import SimpleNamespace
from typing import Any

import pytest
import websockets
import websockets.asyncio.server

from wattpilot_api.client import Wattpilot
from wattpilot_api.exceptions import AuthenticationError, ConnectionError, PropertyError
from wattpilot_api.models import CloudInfo, LoadMode

from .conftest import (
    SAMPLE_AUTH_REQUIRED,
    SAMPLE_AUTH_SUCCESS,
    SAMPLE_DELTA_STATUS,
    SAMPLE_FULL_STATUS,
    SAMPLE_HELLO,
    SAMPLE_HOST,
    SAMPLE_PASSWORD,
    SAMPLE_SERIAL,
    MockWattpilotServer,
)


class TestWattpilotInit:
    def test_local_url(self) -> None:
        wp = Wattpilot("192.168.1.100", "pw")
        assert wp._url == "ws://192.168.1.100/ws"
        assert wp.connected is False

    def test_cloud_url(self) -> None:
        wp = Wattpilot("unused", "pw", serial="ABCD1234", cloud=True)
        assert "wss://app.wattpilot.io/app/ABCD1234" in wp._url
        assert "version=1.2.9" in wp._url

    def test_cloud_url_no_serial(self) -> None:
        wp = Wattpilot("unused", "pw", cloud=True)
        assert "wss://app.wattpilot.io/app/" in wp._url

    def test_initial_state(self) -> None:
        wp = Wattpilot("host", "pw")
        assert wp.connected is False
        assert wp.properties_initialized is False
        assert wp.all_properties == {}
        assert wp.serial == ""
        assert wp.name == ""
        assert wp.power is None
        assert wp.amp is None


class TestWattpilotConnect:
    async def test_connect_and_authenticate(self, mock_server: MockWattpilotServer) -> None:
        wp = Wattpilot(
            SAMPLE_HOST,
            SAMPLE_PASSWORD,
            serial=SAMPLE_SERIAL,
            connect_timeout=5.0,
            init_timeout=5.0,
        )
        wp._url = f"ws://127.0.0.1:{mock_server.port}/ws"
        await wp.connect()
        assert wp.connected is True
        assert wp.properties_initialized is True
        assert wp.serial == SAMPLE_SERIAL
        assert wp.name == f"Wattpilot_{SAMPLE_SERIAL}"
        assert wp.manufacturer == "fronius"
        assert wp.device_type == "wattpilot"
        await wp.disconnect()

    async def test_context_manager(self, mock_server: MockWattpilotServer) -> None:
        wp = Wattpilot(
            SAMPLE_HOST,
            SAMPLE_PASSWORD,
            serial=SAMPLE_SERIAL,
            connect_timeout=5.0,
            init_timeout=5.0,
        )
        wp._url = f"ws://127.0.0.1:{mock_server.port}/ws"
        async with wp:
            assert wp.connected is True
        assert wp.connected is False

    async def test_auth_failure(self, mock_server: MockWattpilotServer) -> None:
        mock_server.auth_success = False
        wp = Wattpilot(
            SAMPLE_HOST,
            SAMPLE_PASSWORD,
            serial=SAMPLE_SERIAL,
            connect_timeout=5.0,
            init_timeout=5.0,
        )
        wp._url = f"ws://127.0.0.1:{mock_server.port}/ws"
        with pytest.raises(AuthenticationError, match="Wrong password"):
            await wp.connect()
        await wp.disconnect()

    async def test_double_connect(self, wattpilot_client: Wattpilot) -> None:
        # Second connect should be a no-op
        await wattpilot_client.connect()
        assert wattpilot_client.connected is True
        assert wattpilot_client.properties_initialized is True

    async def test_connect_early_return_init_timeout(
        self,
    ) -> None:
        """connect() early return raises on init timeout if not initialized."""
        wp = Wattpilot("host", "pw", init_timeout=0.1)
        # Simulate: connected but not initialized
        wp._connected = True
        wp._all_props_initialized = False
        wp._initialized_event.clear()

        with pytest.raises(ConnectionError, match="initialization"):
            await wp.connect()
        assert wp.connected is False

    async def test_disconnect_not_connected(self) -> None:
        wp = Wattpilot("host", "pw")
        await wp.disconnect()  # Should not raise


class TestWattpilotProperties:
    async def test_full_status_properties(self, wattpilot_client: Wattpilot) -> None:
        wp = wattpilot_client
        assert wp.amp == 16
        assert wp.allow_charging is True
        assert wp.car_connected == 2
        assert wp.mode == 3
        assert wp.access_state == 0
        assert wp.error_state == 1
        assert wp.cable_lock == 0
        assert wp.cable_type == 20
        assert wp.frequency == 50.0
        assert wp.phases == 7
        assert wp.energy_counter_since_start == 1234.5
        assert wp.energy_counter_total == 56789.0
        assert wp.cae is True
        assert wp.cak == "testapikey"
        assert wp.firmware == "40.1"
        assert wp.wifi_ssid == "MyWiFi"
        assert wp.version == "36.3"

    async def test_nrg_properties(self, wattpilot_client: Wattpilot) -> None:
        wp = wattpilot_client
        assert wp.voltage1 == 230
        assert wp.voltage2 == 231
        assert wp.voltage3 == 232
        assert wp.voltage_n == 0
        assert wp.amps1 == 10.5
        assert wp.amps2 == 11.0
        assert wp.amps3 == 10.8
        assert wp.power1 == pytest.approx(2.415, rel=1e-3)
        assert wp.power2 == pytest.approx(2.541, rel=1e-3)
        assert wp.power3 == pytest.approx(2.506, rel=1e-3)
        assert wp.power_n == 0.0
        assert wp.power == pytest.approx(7.462, rel=1e-3)

    async def test_all_properties_dict(self, wattpilot_client: Wattpilot) -> None:
        props = wattpilot_client.all_properties
        assert isinstance(props, dict)
        assert "amp" in props
        assert "nrg" in props
        assert props["amp"] == 16

    async def test_delta_status_updates(
        self,
        wattpilot_client: Wattpilot,
        mock_server: MockWattpilotServer,
    ) -> None:
        await mock_server.send_to_all(SAMPLE_DELTA_STATUS)
        await asyncio.sleep(0.1)
        assert wattpilot_client.amp == 10
        assert wattpilot_client.voltage1 == 235

    async def test_device_info(self, wattpilot_client: Wattpilot) -> None:
        assert wattpilot_client.hostname == f"Wattpilot_{SAMPLE_SERIAL}"
        assert wattpilot_client.protocol == 2
        assert wattpilot_client.secured == 1


class TestWattpilotCommands:
    async def test_set_property(self, wattpilot_client: Wattpilot) -> None:
        await wattpilot_client.set_property("amp", 10)
        await asyncio.sleep(0.1)
        assert wattpilot_client.amp == 10

    async def test_set_power(self, wattpilot_client: Wattpilot) -> None:
        await wattpilot_client.set_power(8)
        await asyncio.sleep(0.1)
        assert wattpilot_client.amp == 8

    async def test_set_mode(self, wattpilot_client: Wattpilot) -> None:
        await wattpilot_client.set_mode(LoadMode.ECO)
        await asyncio.sleep(0.1)
        assert wattpilot_client.mode == 4

    async def test_send_not_connected(self) -> None:
        wp = Wattpilot("host", "pw")
        with pytest.raises(ConnectionError, match="Not connected"):
            await wp._send({"type": "test"})


class TestWattpilotCallbacks:
    async def test_sync_property_callback(
        self,
        wattpilot_client: Wattpilot,
        mock_server: MockWattpilotServer,
    ) -> None:
        received: list[tuple[str, Any]] = []

        def callback(name: str, value: Any) -> None:
            received.append((name, value))

        unsub = wattpilot_client.on_property_change(callback)
        await mock_server.send_to_all({"type": "deltaStatus", "status": {"amp": 7}})
        await asyncio.sleep(0.1)

        assert any(name == "amp" and value == 7 for name, value in received)
        unsub()

    async def test_async_property_callback(
        self,
        wattpilot_client: Wattpilot,
        mock_server: MockWattpilotServer,
    ) -> None:
        received: list[tuple[str, Any]] = []

        async def callback(name: str, value: Any) -> None:
            received.append((name, value))

        unsub = wattpilot_client.on_property_change(callback)
        await mock_server.send_to_all({"type": "deltaStatus", "status": {"amp": 6}})
        await asyncio.sleep(0.2)

        assert any(name == "amp" and value == 6 for name, value in received)
        unsub()

    async def test_message_callback(
        self,
        wattpilot_client: Wattpilot,
        mock_server: MockWattpilotServer,
    ) -> None:
        received: list[dict[str, Any]] = []

        def callback(msg: dict[str, Any]) -> None:
            received.append(msg)

        unsub = wattpilot_client.on_message(callback)
        await mock_server.send_to_all({"type": "deltaStatus", "status": {"amp": 5}})
        await asyncio.sleep(0.1)

        assert any(msg["type"] == "deltaStatus" for msg in received)
        unsub()

    async def test_unsubscribe(
        self,
        wattpilot_client: Wattpilot,
        mock_server: MockWattpilotServer,
    ) -> None:
        received: list[tuple[str, Any]] = []

        def callback(name: str, value: Any) -> None:
            received.append((name, value))

        unsub = wattpilot_client.on_property_change(callback)
        unsub()
        await mock_server.send_to_all({"type": "deltaStatus", "status": {"amp": 99}})
        await asyncio.sleep(0.1)

        assert not any(name == "amp" and value == 99 for name, value in received)


class TestWattpilotStr:
    async def test_connected_str(self, wattpilot_client: Wattpilot) -> None:
        s = str(wattpilot_client)
        assert "Wattpilot" in s
        assert SAMPLE_SERIAL in s
        assert "Connected: True" in s

    def test_disconnected_str(self) -> None:
        wp = Wattpilot("host", "pw")
        assert str(wp) == "Not connected"


class TestWattpilotPartialStatus:
    async def test_partial_full_status(self, mock_server: MockWattpilotServer) -> None:
        mock_server.send_partial = True
        wp = Wattpilot(
            SAMPLE_HOST,
            SAMPLE_PASSWORD,
            serial=SAMPLE_SERIAL,
            connect_timeout=5.0,
            init_timeout=5.0,
        )
        wp._url = f"ws://127.0.0.1:{mock_server.port}/ws"
        await wp.connect()
        assert wp.connected is True
        assert wp.properties_initialized is True
        assert wp.amp == 16  # From the non-partial full status
        await wp.disconnect()


class TestWattpilotResponse:
    async def test_failed_response(
        self,
        wattpilot_client: Wattpilot,
        mock_server: MockWattpilotServer,
    ) -> None:
        # Send a failed response directly
        await mock_server.send_to_all(
            {
                "type": "response",
                "requestId": "99",
                "success": False,
                "message": "value must be bool",
            }
        )
        await asyncio.sleep(0.1)
        # Should not crash, just log

    async def test_unknown_message_type(
        self,
        wattpilot_client: Wattpilot,
        mock_server: MockWattpilotServer,
    ) -> None:
        await mock_server.send_to_all({"type": "unknownType", "data": 123})
        await asyncio.sleep(0.1)
        # Should not crash

    async def test_clear_inverters(
        self,
        wattpilot_client: Wattpilot,
        mock_server: MockWattpilotServer,
    ) -> None:
        await mock_server.send_to_all({"type": "clearInverters", "partial": True})
        await asyncio.sleep(0.1)

    async def test_update_inverter(
        self,
        wattpilot_client: Wattpilot,
        mock_server: MockWattpilotServer,
    ) -> None:
        await mock_server.send_to_all({"type": "updateInverter", "partial": False, "id": "test"})
        await asyncio.sleep(0.1)


class TestWattpilotTimeout:
    async def test_auth_timeout(self) -> None:
        """Test that connect raises ConnectionError on auth timeout."""

        async def _no_auth_handler(ws: Any) -> None:
            await ws.send(json.dumps(SAMPLE_HELLO))
            await ws.send(json.dumps(SAMPLE_AUTH_REQUIRED))
            async for _ in ws:
                pass  # Don't respond to auth

        server = await websockets.asyncio.server.serve(_no_auth_handler, "127.0.0.1", 0)
        port = None
        for sock in server.sockets:
            port = sock.getsockname()[1]
            break
        try:
            wp = Wattpilot(
                SAMPLE_HOST,
                SAMPLE_PASSWORD,
                serial=SAMPLE_SERIAL,
                connect_timeout=0.5,
                init_timeout=0.5,
            )
            wp._url = f"ws://127.0.0.1:{port}/ws"
            with pytest.raises(ConnectionError, match="Timeout waiting for authentication"):
                await wp.connect()
        finally:
            server.close()
            await server.wait_closed()

    async def test_init_timeout(self) -> None:
        """Test that connect raises ConnectionError on init timeout."""

        async def _no_status_handler(ws: Any) -> None:
            await ws.send(json.dumps(SAMPLE_HELLO))
            await ws.send(json.dumps(SAMPLE_AUTH_REQUIRED))
            async for raw in ws:
                msg = json.loads(raw)
                if msg["type"] == "auth":
                    await ws.send(json.dumps(SAMPLE_AUTH_SUCCESS))

        server = await websockets.asyncio.server.serve(_no_status_handler, "127.0.0.1", 0)
        port = None
        for sock in server.sockets:
            port = sock.getsockname()[1]
            break
        try:
            wp = Wattpilot(
                SAMPLE_HOST,
                SAMPLE_PASSWORD,
                serial=SAMPLE_SERIAL,
                connect_timeout=5.0,
                init_timeout=0.5,
            )
            wp._url = f"ws://127.0.0.1:{port}/ws"
            with pytest.raises(
                ConnectionError,
                match="Timeout waiting for property initialization",
            ):
                await wp.connect()
        finally:
            server.close()
            await server.wait_closed()


class TestWattpilotEdgeCases:
    async def test_bytes_message(
        self,
        wattpilot_client: Wattpilot,
        mock_server: MockWattpilotServer,
    ) -> None:
        """Cover the bytes decoding branch in _message_loop."""
        for ws in mock_server._connections:
            msg = json.dumps({"type": "deltaStatus", "status": {"amp": 12}})
            await ws.send(msg.encode("utf-8"))
        await asyncio.sleep(0.1)
        assert wattpilot_client.amp == 12

    async def test_async_message_callback(
        self,
        wattpilot_client: Wattpilot,
        mock_server: MockWattpilotServer,
    ) -> None:
        """Cover the async message callback branch."""
        received: list[dict[str, Any]] = []

        async def async_cb(msg: dict[str, Any]) -> None:
            received.append(msg)

        unsub = wattpilot_client.on_message(async_cb)
        await mock_server.send_to_all({"type": "deltaStatus", "status": {"amp": 3}})
        await asyncio.sleep(0.2)

        assert any(m.get("type") == "deltaStatus" for m in received)
        unsub()

    async def test_fullstatus_without_partial(
        self,
        wattpilot_client: Wattpilot,
        mock_server: MockWattpilotServer,
    ) -> None:
        """Cover _on_full_status else branch (no 'partial' attribute)."""
        await mock_server.send_to_all(
            {
                "type": "fullStatus",
                "status": {"amp": 20},
            }
        )
        await asyncio.sleep(0.1)
        assert wattpilot_client.amp == 20

    async def test_ast_property(
        self,
        wattpilot_client: Wattpilot,
        mock_server: MockWattpilotServer,
    ) -> None:
        """Cover the 'ast' case in _update_property."""
        await mock_server.send_to_all({"type": "deltaStatus", "status": {"ast": 1}})
        await asyncio.sleep(0.1)
        assert wattpilot_client.access_state == 1

    def test_update_hashed_password_empty_password(self) -> None:
        """Cover the early return in _update_hashed_password."""
        wp = Wattpilot("host", "")
        wp._device.serial = "12345678"
        wp._update_hashed_password()
        assert wp._hashed_password == b""

    def test_update_hashed_password_empty_serial(self) -> None:
        """Cover the early return in _update_hashed_password."""
        wp = Wattpilot("host", "password")
        wp._device.serial = ""
        wp._update_hashed_password()
        assert wp._hashed_password == b""


class TestWattpilotAuthVariants:
    async def test_auth_with_explicit_hash_type(self) -> None:
        """Cover authRequired with explicit hash field."""

        async def _hash_handler(ws: Any) -> None:
            await ws.send(json.dumps(SAMPLE_HELLO))
            await ws.send(
                json.dumps(
                    {
                        "type": "authRequired",
                        "token1": "a" * 32,
                        "token2": "b" * 32,
                        "hash": "pbkdf2",
                    }
                )
            )
            async for raw in ws:
                msg = json.loads(raw)
                if msg["type"] == "auth":
                    await ws.send(json.dumps(SAMPLE_AUTH_SUCCESS))
                    await ws.send(json.dumps(SAMPLE_FULL_STATUS))

        server = await websockets.asyncio.server.serve(_hash_handler, "127.0.0.1", 0)
        port = next(s.getsockname()[1] for s in server.sockets)
        try:
            wp = Wattpilot(
                SAMPLE_HOST,
                SAMPLE_PASSWORD,
                serial=SAMPLE_SERIAL,
                connect_timeout=5.0,
                init_timeout=5.0,
            )
            wp._url = f"ws://127.0.0.1:{port}/ws"
            await wp.connect()
            assert wp.connected is True
            await wp.disconnect()
        finally:
            server.close()
            await server.wait_closed()

    async def test_flex_device_bcrypt(self) -> None:
        """Cover the bcrypt fallback for WPFlex devices."""

        async def _flex_handler(ws: Any) -> None:
            hello = dict(SAMPLE_HELLO)
            hello["devicetype"] = "wattpilot_flex"
            await ws.send(json.dumps(hello))
            await ws.send(json.dumps(SAMPLE_AUTH_REQUIRED))
            async for raw in ws:
                msg = json.loads(raw)
                if msg["type"] == "auth":
                    await ws.send(json.dumps(SAMPLE_AUTH_SUCCESS))
                    await ws.send(json.dumps(SAMPLE_FULL_STATUS))

        server = await websockets.asyncio.server.serve(_flex_handler, "127.0.0.1", 0)
        port = next(s.getsockname()[1] for s in server.sockets)
        try:
            wp = Wattpilot(
                SAMPLE_HOST,
                SAMPLE_PASSWORD,
                serial=SAMPLE_SERIAL,
                connect_timeout=5.0,
                init_timeout=5.0,
            )
            wp._url = f"ws://127.0.0.1:{port}/ws"
            await wp.connect()
            assert wp.connected is True
            assert wp._auth_hash_type.value == "bcrypt"
            await wp.disconnect()
        finally:
            server.close()
            await server.wait_closed()


class TestWattpilotDeltaBeforeInit:
    async def test_delta_initializes(self) -> None:
        """Cover delta status marking initialization complete."""

        async def _delta_first_handler(ws: Any) -> None:
            await ws.send(json.dumps(SAMPLE_HELLO))
            await ws.send(json.dumps(SAMPLE_AUTH_REQUIRED))
            async for raw in ws:
                msg = json.loads(raw)
                if msg["type"] == "auth":
                    await ws.send(json.dumps(SAMPLE_AUTH_SUCCESS))
                    await ws.send(json.dumps({"type": "deltaStatus", "status": {"amp": 7}}))

        server = await websockets.asyncio.server.serve(_delta_first_handler, "127.0.0.1", 0)
        port = next(s.getsockname()[1] for s in server.sockets)
        try:
            wp = Wattpilot(
                SAMPLE_HOST,
                SAMPLE_PASSWORD,
                serial=SAMPLE_SERIAL,
                connect_timeout=5.0,
                init_timeout=5.0,
            )
            wp._url = f"ws://127.0.0.1:{port}/ws"
            await wp.connect()
            assert wp.connected is True
            assert wp.properties_initialized is True
            assert wp.amp == 7
            await wp.disconnect()
        finally:
            server.close()
            await server.wait_closed()


class TestWattpilotConnectionClosed:
    async def test_server_closes_connection(self, mock_server: MockWattpilotServer) -> None:
        """Cover the ConnectionClosed exception handler in _message_loop."""
        wp = Wattpilot(
            SAMPLE_HOST,
            SAMPLE_PASSWORD,
            serial=SAMPLE_SERIAL,
            connect_timeout=5.0,
            init_timeout=5.0,
        )
        wp._url = f"ws://127.0.0.1:{mock_server.port}/ws"
        await wp.connect()
        assert wp.connected is True

        # Close all server-side connections
        for ws in list(mock_server._connections):
            await ws.close()
        await asyncio.sleep(0.2)
        assert wp.connected is False


# ---- Issue #5: Additional typed properties ----


class TestNewProperties:
    """Tests for additional typed properties from issue #5."""

    async def test_device_info_properties(self, wattpilot_client: Wattpilot) -> None:
        assert wattpilot_client.variant == "11kW"
        assert wattpilot_client.model == "wattpilot_home"

    async def test_charging_state_properties(self, wattpilot_client: Wattpilot) -> None:
        assert wattpilot_client.car_state == 2
        assert wattpilot_client.cable_unlock_status == 0
        assert wattpilot_client.charging_reason == 1
        assert wattpilot_client.force_state == 0
        assert wattpilot_client.active_transaction_chip is None

    async def test_config_properties(self, wattpilot_client: Wattpilot) -> None:
        assert wattpilot_client.button_lock == 0
        assert wattpilot_client.daylight_saving == 0
        assert wattpilot_client.phase_switch_mode == 1

    async def test_diagnostic_properties(self, wattpilot_client: Wattpilot) -> None:
        assert wattpilot_client.lock_feedback == 0
        assert wattpilot_client.effective_lock_setting == 0
        assert wattpilot_client.local_time == "2026-02-11T12:00:00"
        assert wattpilot_client.wifi_signal_strength == -65
        assert wattpilot_client.temperature == [25.5, 26.0]
        assert wattpilot_client.uptime_ms == 86400000
        assert wattpilot_client.reboot_count == 5
        assert wattpilot_client.websocket_queue_size == 0
        assert wattpilot_client.http_clients == 2
        assert wattpilot_client.websocket_clients == 1
        assert wattpilot_client.wifi_status == 3

    async def test_inverter_and_wifi_info(self, wattpilot_client: Wattpilot) -> None:
        cci = wattpilot_client.inverter_info
        assert isinstance(cci, dict) or hasattr(cci, "__dict__")
        ccw = wattpilot_client.wifi_connection_info
        assert ccw is not None

    async def test_rfid_cards(self, wattpilot_client: Wattpilot) -> None:
        cards = wattpilot_client.rfid_cards
        assert isinstance(cards, list)
        assert len(cards) == 1

    async def test_pv_solar_properties(self, wattpilot_client: Wattpilot) -> None:
        assert wattpilot_client.pv_surplus_enabled is False
        assert wattpilot_client.pv_surplus_start_power == 1500.0
        assert wattpilot_client.pv_battery_threshold == 80.0
        assert wattpilot_client.min_charging_time == 300
        assert wattpilot_client.next_trip_energy == 20000.0
        assert wattpilot_client.next_trip_time == 28800

    async def test_firmware_properties(self, wattpilot_client: Wattpilot) -> None:
        assert wattpilot_client.installed_firmware_version == "40.1"
        assert wattpilot_client.available_firmware_versions == ["40.2", "40.3"]
        assert wattpilot_client.firmware_update_available is True

    async def test_cloud_properties(self, wattpilot_client: Wattpilot) -> None:
        assert wattpilot_client.cloud_enabled is True
        assert wattpilot_client.cloud_api_key == "testapikey"
        assert wattpilot_client.cloud_api_url is not None
        assert SAMPLE_SERIAL in wattpilot_client.cloud_api_url  # type: ignore[operator]

    async def test_firmware_not_available(
        self,
        wattpilot_client: Wattpilot,
        mock_server: MockWattpilotServer,
    ) -> None:
        """firmware_update_available is False when onv is empty."""
        await mock_server.send_to_all({"type": "deltaStatus", "status": {"onv": []}})
        await asyncio.sleep(0.1)
        assert wattpilot_client.firmware_update_available is False

    async def test_firmware_available_single_string(
        self,
        wattpilot_client: Wattpilot,
        mock_server: MockWattpilotServer,
    ) -> None:
        """available_firmware_versions handles a single string value."""
        await mock_server.send_to_all({"type": "deltaStatus", "status": {"onv": "41.0"}})
        await asyncio.sleep(0.1)
        assert wattpilot_client.available_firmware_versions == ["41.0"]

    async def test_firmware_available_empty_string(
        self,
        wattpilot_client: Wattpilot,
        mock_server: MockWattpilotServer,
    ) -> None:
        """available_firmware_versions handles empty string."""
        await mock_server.send_to_all({"type": "deltaStatus", "status": {"onv": ""}})
        await asyncio.sleep(0.1)
        assert wattpilot_client.available_firmware_versions == []

    async def test_firmware_update_available_no_firmware(self) -> None:
        """firmware_update_available when firmware is not yet received."""
        wp = Wattpilot("host", "pw")
        wp._all_props["onv"] = ["41.0"]
        assert wp.firmware_update_available is True

    async def test_firmware_update_same_version(
        self,
        wattpilot_client: Wattpilot,
        mock_server: MockWattpilotServer,
    ) -> None:
        """firmware_update_available is False when onv matches installed."""
        await mock_server.send_to_all({"type": "deltaStatus", "status": {"onv": ["40.1"]}})
        await asyncio.sleep(0.1)
        assert wattpilot_client.firmware_update_available is False

    async def test_cloud_url_disabled(self) -> None:
        """cloud_api_url is None when cloud is disabled."""
        wp = Wattpilot("host", "pw")
        assert wp.cloud_api_url is None

    async def test_cloud_url_no_serial(self) -> None:
        """cloud_api_url is None when serial is empty."""
        wp = Wattpilot("host", "pw")
        wp._cae = True
        assert wp.cloud_api_url is None

    def test_uninitialized_new_properties(self) -> None:
        """New properties return None when client is not connected."""
        wp = Wattpilot("host", "pw")
        assert wp.variant is None
        assert wp.model is None
        assert wp.car_state is None
        assert wp.force_state is None
        assert wp.temperature is None
        assert wp.rfid_cards is None
        assert wp.pv_surplus_enabled is None
        assert wp.available_firmware_versions == []
        assert wp.firmware_update_available is False


# ---- Issue #2: Type coercion ----


class TestTypeCoercion:
    """Tests for set_property() type coercion from issue #2."""

    def test_coerce_bool_native(self) -> None:
        wp = Wattpilot("host", "pw")
        assert wp._coerce_value("cae", True) is True
        assert wp._coerce_value("cae", False) is False

    def test_coerce_bool_from_string(self) -> None:
        wp = Wattpilot("host", "pw")
        assert wp._coerce_value("cae", "true") is True
        assert wp._coerce_value("cae", "True") is True
        assert wp._coerce_value("cae", "1") is True
        assert wp._coerce_value("cae", "yes") is True
        assert wp._coerce_value("cae", "false") is False
        assert wp._coerce_value("cae", "False") is False
        assert wp._coerce_value("cae", "0") is False
        assert wp._coerce_value("cae", "no") is False

    def test_coerce_bool_from_int(self) -> None:
        wp = Wattpilot("host", "pw")
        assert wp._coerce_value("cae", 1) is True
        assert wp._coerce_value("cae", 0) is False

    def test_coerce_bool_invalid_string(self) -> None:
        wp = Wattpilot("host", "pw")
        with pytest.raises(PropertyError, match="Cannot convert"):
            wp._coerce_value("cae", "maybe")

    def test_coerce_bool_invalid_type(self) -> None:
        wp = Wattpilot("host", "pw")
        with pytest.raises(PropertyError, match="Cannot convert"):
            wp._coerce_value("cae", [1, 2, 3])

    def test_coerce_int_native(self) -> None:
        wp = Wattpilot("host", "pw")
        assert wp._coerce_value("amp", 16) == 16

    def test_coerce_int_from_bool(self) -> None:
        wp = Wattpilot("host", "pw")
        assert wp._coerce_value("amp", True) == 1

    def test_coerce_int_from_float(self) -> None:
        wp = Wattpilot("host", "pw")
        assert wp._coerce_value("amp", 16.7) == 16

    def test_coerce_int_from_string(self) -> None:
        wp = Wattpilot("host", "pw")
        assert wp._coerce_value("amp", "16") == 16

    def test_coerce_int_from_float_string(self) -> None:
        wp = Wattpilot("host", "pw")
        assert wp._coerce_value("amp", "16.7") == 16

    def test_coerce_int_invalid_string(self) -> None:
        wp = Wattpilot("host", "pw")
        with pytest.raises(PropertyError, match="Cannot convert"):
            wp._coerce_value("amp", "not_a_number")

    def test_coerce_int_invalid_type(self) -> None:
        wp = Wattpilot("host", "pw")
        with pytest.raises(PropertyError, match="Cannot convert"):
            wp._coerce_value("amp", [1, 2])

    def test_coerce_float_native(self) -> None:
        wp = Wattpilot("host", "pw")
        # fst is a float property (pv surplus start power)
        assert wp._coerce_value("fst", 1500.0) == 1500.0

    def test_coerce_float_from_bool(self) -> None:
        wp = Wattpilot("host", "pw")
        assert wp._coerce_value("fst", True) == 1.0

    def test_coerce_float_from_int(self) -> None:
        wp = Wattpilot("host", "pw")
        assert wp._coerce_value("fst", 1500) == 1500.0

    def test_coerce_float_from_string(self) -> None:
        wp = Wattpilot("host", "pw")
        assert wp._coerce_value("fst", "1500.5") == 1500.5

    def test_coerce_float_invalid_string(self) -> None:
        wp = Wattpilot("host", "pw")
        with pytest.raises(PropertyError, match="Cannot convert"):
            wp._coerce_value("fst", "abc")

    def test_coerce_float_invalid_type(self) -> None:
        wp = Wattpilot("host", "pw")
        with pytest.raises(PropertyError, match="Cannot convert"):
            wp._coerce_value("fst", {"key": "val"})

    def test_coerce_string(self) -> None:
        wp = Wattpilot("host", "pw")
        # cak is a string property (cloud API key)
        assert wp._coerce_value("cak", "mykey") == "mykey"
        assert wp._coerce_value("cak", 40) == "40"

    def test_coerce_simplenamespace(self) -> None:
        wp = Wattpilot("host", "pw")
        ns = SimpleNamespace(a=1, b="hello")
        result = wp._coerce_value("anything", ns)
        assert result == {"a": 1, "b": "hello"}

    def test_coerce_unknown_property(self) -> None:
        wp = Wattpilot("host", "pw")
        assert wp._coerce_value("unknown_prop_xyz", 42) == 42

    def test_coerce_no_json_type(self) -> None:
        """Properties without jsonType in the API def should pass through."""
        wp = Wattpilot("host", "pw")
        api_def = wp._get_api_def()
        # Add a fake property with no jsonType
        api_def.properties["_test_no_type"] = {"key": "_test_no_type"}
        assert wp._coerce_value("_test_no_type", "whatever") == "whatever"

    def test_coerce_array_passthrough(self) -> None:
        """Array/object types pass through without conversion."""
        wp = Wattpilot("host", "pw")
        val = [1, 2, 3]
        # nrg is an array type
        assert wp._coerce_value("nrg", val) is val

    def test_get_api_def_cached(self) -> None:
        """API definition is loaded once and cached."""
        wp = Wattpilot("host", "pw")
        api1 = wp._get_api_def()
        api2 = wp._get_api_def()
        assert api1 is api2


# ---- Issue #3: set_next_trip ----


class TestSetNextTrip:
    async def test_set_next_trip_from_time(self, wattpilot_client: Wattpilot) -> None:
        """set_next_trip with a time object."""
        t = datetime.time(8, 0, 0)  # 8:00 AM
        await wattpilot_client.set_next_trip(t)
        await asyncio.sleep(0.1)
        assert wattpilot_client.next_trip_time == 28800  # 8*3600

    async def test_set_next_trip_from_datetime(self, wattpilot_client: Wattpilot) -> None:
        """set_next_trip with a datetime extracts time component."""
        dt = datetime.datetime(2026, 6, 15, 7, 30, 0)
        await wattpilot_client.set_next_trip(dt)
        await asyncio.sleep(0.1)
        assert wattpilot_client.next_trip_time == 27000  # 7*3600 + 30*60

    async def test_set_next_trip_with_dst(
        self,
        wattpilot_client: Wattpilot,
        mock_server: MockWattpilotServer,
    ) -> None:
        """set_next_trip adjusts +3600 when DST is enabled."""
        # Enable DST on the charger
        await mock_server.send_to_all({"type": "deltaStatus", "status": {"tds": 1}})
        await asyncio.sleep(0.1)

        t = datetime.time(8, 0, 0)
        await wattpilot_client.set_next_trip(t)
        await asyncio.sleep(0.1)
        # 8*3600 + 3600 = 32400
        assert wattpilot_client.next_trip_time == 32400

    async def test_set_next_trip_with_us_dst(
        self,
        wattpilot_client: Wattpilot,
        mock_server: MockWattpilotServer,
    ) -> None:
        """set_next_trip adjusts +3600 when US Daylight Time (tds=2)."""
        await mock_server.send_to_all({"type": "deltaStatus", "status": {"tds": 2}})
        await asyncio.sleep(0.1)

        t = datetime.time(8, 0, 0)
        await wattpilot_client.set_next_trip(t)
        await asyncio.sleep(0.1)
        # 8*3600 + 3600 = 32400
        assert wattpilot_client.next_trip_time == 32400

    async def test_set_next_trip_no_dst(self, wattpilot_client: Wattpilot) -> None:
        """set_next_trip without DST (tds=0)."""
        t = datetime.time(6, 30, 0)
        await wattpilot_client.set_next_trip(t)
        await asyncio.sleep(0.1)
        assert wattpilot_client.next_trip_time == 23400  # 6*3600 + 30*60

    async def test_set_next_trip_energy(self, wattpilot_client: Wattpilot) -> None:
        """set_next_trip_energy sets esk=True then fte."""
        await wattpilot_client.set_next_trip_energy(15.0)
        await asyncio.sleep(0.2)
        # esk should have been set to True, fte to 15.0
        assert wattpilot_client.all_properties.get("esk") is True
        assert wattpilot_client.next_trip_energy == 15.0


# ---- Issue #4: Cloud API ----


class TestCloudAPI:
    async def test_enable_cloud_api(self, wattpilot_client: Wattpilot) -> None:
        """enable_cloud_api returns CloudInfo when cak is already available."""
        info = await wattpilot_client.enable_cloud_api(timeout=2.0)
        assert isinstance(info, CloudInfo)
        assert info.enabled is True
        assert info.api_key == "testapikey"
        assert SAMPLE_SERIAL in info.url

    async def test_disable_cloud_api(self, wattpilot_client: Wattpilot) -> None:
        """disable_cloud_api sets cae to False."""
        await wattpilot_client.disable_cloud_api()
        await asyncio.sleep(0.1)
        assert wattpilot_client.cloud_enabled is False

    async def test_enable_cloud_api_timeout(self) -> None:
        """enable_cloud_api raises on timeout when API key never appears."""

        async def _no_cak_handler(ws: Any) -> None:
            await ws.send(json.dumps(SAMPLE_HELLO))
            await ws.send(json.dumps(SAMPLE_AUTH_REQUIRED))
            async for raw in ws:
                msg = json.loads(raw)
                if msg["type"] == "auth":
                    await ws.send(json.dumps(SAMPLE_AUTH_SUCCESS))
                    status = dict(SAMPLE_FULL_STATUS)
                    status["status"] = dict(status["status"])
                    status["status"]["cak"] = ""
                    await ws.send(json.dumps(status))
                elif msg["type"] == "securedMsg":
                    inner = json.loads(msg["data"])
                    await ws.send(
                        json.dumps(
                            {
                                "type": "response",
                                "requestId": inner["requestId"],
                                "success": True,
                                "status": {inner["key"]: inner["value"]},
                            }
                        )
                    )

        server = await websockets.asyncio.server.serve(_no_cak_handler, "127.0.0.1", 0)
        port = next(s.getsockname()[1] for s in server.sockets)
        try:
            wp = Wattpilot(
                SAMPLE_HOST,
                SAMPLE_PASSWORD,
                serial=SAMPLE_SERIAL,
                connect_timeout=5.0,
                init_timeout=5.0,
            )
            wp._url = f"ws://127.0.0.1:{port}/ws"
            await wp.connect()

            with pytest.raises(ConnectionError, match="Timeout waiting for cloud API key"):
                await wp.enable_cloud_api(timeout=2.0)
        finally:
            await wp.disconnect()
            server.close()
            await server.wait_closed()


# ---- Issue #6: Firmware update ----


class TestFirmwareUpdate:
    async def test_install_firmware_no_versions(self, wattpilot_client: Wattpilot) -> None:
        """install_firmware_update raises when no versions available."""
        # Clear onv
        wattpilot_client._all_props["onv"] = []
        with pytest.raises(PropertyError, match="No firmware updates available"):
            await wattpilot_client.install_firmware_update()

    async def test_install_firmware_explicit_version(self) -> None:
        """install_firmware_update with explicit version, full reboot cycle."""

        async def _firmware_handler(ws: Any) -> None:
            await ws.send(json.dumps(SAMPLE_HELLO))
            await ws.send(json.dumps(SAMPLE_AUTH_REQUIRED))
            async for raw in ws:
                msg = json.loads(raw)
                if msg["type"] == "auth":
                    await ws.send(json.dumps(SAMPLE_AUTH_SUCCESS))
                    await ws.send(json.dumps(SAMPLE_FULL_STATUS))
                elif msg["type"] == "securedMsg":
                    inner = json.loads(msg["data"])
                    await ws.send(
                        json.dumps(
                            {
                                "type": "response",
                                "requestId": inner["requestId"],
                                "success": True,
                                "status": {inner["key"]: inner["value"]},
                            }
                        )
                    )
                    if inner.get("key") == "oct":
                        await asyncio.sleep(0.1)
                        await ws.close()
                        return

        server = await websockets.asyncio.server.serve(_firmware_handler, "127.0.0.1", 0)
        port = next(s.getsockname()[1] for s in server.sockets)
        try:
            wp = Wattpilot(
                SAMPLE_HOST,
                SAMPLE_PASSWORD,
                serial=SAMPLE_SERIAL,
                connect_timeout=5.0,
                init_timeout=5.0,
            )
            wp._url = f"ws://127.0.0.1:{port}/ws"
            await wp.connect()
            assert wp.connected is True

            await wp.install_firmware_update("40.3", timeout=15.0)
            assert wp.connected is True
        finally:
            await wp.disconnect()
            server.close()
            await server.wait_closed()

    async def test_install_firmware_auto_version(self) -> None:
        """install_firmware_update picks first available version when none specified."""

        async def _firmware_handler(ws: Any) -> None:
            await ws.send(json.dumps(SAMPLE_HELLO))
            await ws.send(json.dumps(SAMPLE_AUTH_REQUIRED))
            async for raw in ws:
                msg = json.loads(raw)
                if msg["type"] == "auth":
                    await ws.send(json.dumps(SAMPLE_AUTH_SUCCESS))
                    await ws.send(json.dumps(SAMPLE_FULL_STATUS))
                elif msg["type"] == "securedMsg":
                    inner = json.loads(msg["data"])
                    await ws.send(
                        json.dumps(
                            {
                                "type": "response",
                                "requestId": inner["requestId"],
                                "success": True,
                                "status": {inner["key"]: inner["value"]},
                            }
                        )
                    )
                    if inner.get("key") == "oct":
                        await asyncio.sleep(0.1)
                        await ws.close()
                        return

        server = await websockets.asyncio.server.serve(_firmware_handler, "127.0.0.1", 0)
        port = next(s.getsockname()[1] for s in server.sockets)
        try:
            wp = Wattpilot(
                SAMPLE_HOST,
                SAMPLE_PASSWORD,
                serial=SAMPLE_SERIAL,
                connect_timeout=5.0,
                init_timeout=5.0,
            )
            wp._url = f"ws://127.0.0.1:{port}/ws"
            await wp.connect()

            await wp.install_firmware_update(timeout=15.0)
            assert wp.connected is True
        finally:
            await wp.disconnect()
            server.close()
            await server.wait_closed()

    async def test_install_firmware_disconnect_timeout(self, wattpilot_client: Wattpilot) -> None:
        """install_firmware_update raises when charger doesn't disconnect."""
        with pytest.raises(ConnectionError, match="did not disconnect"):
            await wattpilot_client.install_firmware_update("40.3", timeout=1.5)

    async def test_install_firmware_reconnect_timeout(self) -> None:
        """install_firmware_update raises when charger doesn't come back."""
        call_count = 0

        async def _handler(ws: Any) -> None:
            nonlocal call_count
            call_count += 1

            if call_count > 1:
                # Subsequent connections: never respond to auth → triggers timeout
                async for _ in ws:
                    pass
                return

            await ws.send(json.dumps(SAMPLE_HELLO))
            await ws.send(json.dumps(SAMPLE_AUTH_REQUIRED))
            async for raw in ws:
                msg = json.loads(raw)
                if msg["type"] == "auth":
                    await ws.send(json.dumps(SAMPLE_AUTH_SUCCESS))
                    await ws.send(json.dumps(SAMPLE_FULL_STATUS))
                elif msg["type"] == "securedMsg":
                    inner = json.loads(msg["data"])
                    await ws.send(
                        json.dumps(
                            {
                                "type": "response",
                                "requestId": inner["requestId"],
                                "success": True,
                                "status": {inner["key"]: inner["value"]},
                            }
                        )
                    )
                    if inner.get("key") == "oct":
                        await asyncio.sleep(0.1)
                        await ws.close()
                        return

        server = await websockets.asyncio.server.serve(_handler, "127.0.0.1", 0)
        port = next(s.getsockname()[1] for s in server.sockets)
        try:
            wp = Wattpilot(
                SAMPLE_HOST,
                SAMPLE_PASSWORD,
                serial=SAMPLE_SERIAL,
                connect_timeout=0.3,
                init_timeout=0.3,
            )
            wp._url = f"ws://127.0.0.1:{port}/ws"
            await wp.connect()

            with pytest.raises(ConnectionError, match="Timeout reconnecting"):
                await wp.install_firmware_update("40.3", timeout=3.0)
        finally:
            await wp.disconnect()
            server.close()
            await server.wait_closed()

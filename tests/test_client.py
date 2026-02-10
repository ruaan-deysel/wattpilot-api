"""Tests for the async Wattpilot client."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
import websockets
import websockets.asyncio.server

from wattpilot_api.client import Wattpilot
from wattpilot_api.exceptions import AuthenticationError, ConnectionError
from wattpilot_api.models import LoadMode

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

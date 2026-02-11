"""Shared fixtures for the wattpilot-api test suite."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

import pytest
import websockets
import websockets.asyncio.server

from wattpilot_api.client import Wattpilot
from wattpilot_api.definition import ApiDefinition, load_api_definition

# ---- Sample data ----

SAMPLE_SERIAL = "12345678"
SAMPLE_PASSWORD = "testpassword"
SAMPLE_HOST = "127.0.0.1"

SAMPLE_HELLO = {
    "type": "hello",
    "serial": SAMPLE_SERIAL,
    "hostname": f"Wattpilot_{SAMPLE_SERIAL}",
    "friendly_name": "My Wattpilot",
    "manufacturer": "fronius",
    "devicetype": "wattpilot",
    "version": "36.3",
    "protocol": 2,
    "secured": 1,
}

SAMPLE_AUTH_REQUIRED = {
    "type": "authRequired",
    "token1": "a" * 32,
    "token2": "b" * 32,
}

SAMPLE_AUTH_SUCCESS = {
    "type": "authSuccess",
}

SAMPLE_FULL_STATUS = {
    "type": "fullStatus",
    "partial": False,
    "status": {
        "alw": True,
        "amp": 16,
        "car": 2,
        "lmo": 3,
        "acs": 0,
        "err": 1,
        "ust": 0,
        "cbl": 20,
        "fhz": 50.0,
        "pha": 7,
        "wh": 1234.5,
        "eto": 56789.0,
        "cae": True,
        "cak": "testapikey",
        "fwv": "40.1",
        "wss": "MyWiFi",
        "version": "36.3",
        "nrg": [230, 231, 232, 0, 10.5, 11.0, 10.8, 2415, 2541, 2506, 0, 7462, 0, 0, 0, 0],
        # Additional properties for issue #5
        "var": "11kW",
        "typ": "wattpilot_home",
        "cus": 0,
        "modelStatus": 1,
        "frc": 0,
        "trx": None,
        "bac": 0,
        "tds": 0,
        "psm": 1,
        "ffb": 0,
        "lck": 0,
        "loc": "2026-02-11T12:00:00",
        "rssi": -65,
        "tma": [25.5, 26.0],
        "rbt": 86400000,
        "rbc": 5,
        "fup": False,
        "fst": 1500.0,
        "fam": 80.0,
        "fmt": 300,
        "fte": 20000.0,
        "ftt": 28800,
        "onv": ["40.2", "40.3"],
        "cards": [{"name": "Card1", "cardId": "abc123", "energy": 100}],
        "cci": {"provider": "SolarInverter"},
        "ccw": {"ssid": "MyWiFi", "ip": "192.168.1.100"},
        "qsw": 0,
        "wcch": 2,
        "wccw": 1,
        "wst": 3,
    },
}

SAMPLE_DELTA_STATUS = {
    "type": "deltaStatus",
    "status": {
        "amp": 10,
        "nrg": [235, 236, 234, 1, 5.0, 5.5, 5.2, 1175, 1298, 1217, 0, 3690, 0, 0, 0, 0],
    },
}


# ---- Mock WebSocket server ----


class MockWattpilotServer:
    """A mock WebSocket server that simulates the Wattpilot protocol."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self.host = host
        self.port = port
        self._server: websockets.asyncio.server.Server | None = None
        self._connections: list[websockets.asyncio.server.ServerConnection] = []
        self.auth_success = True
        self.send_partial = False

    async def start(self) -> int:
        self._server = await websockets.asyncio.server.serve(self._handler, self.host, self.port)
        # Get the actual port
        for sock in self._server.sockets:
            addr = sock.getsockname()
            self.port = addr[1]
            break
        return self.port

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    async def send_to_all(self, msg: dict[str, Any]) -> None:
        for ws in self._connections:
            await ws.send(json.dumps(msg))

    async def _handler(self, ws: websockets.asyncio.server.ServerConnection) -> None:
        self._connections.append(ws)
        try:
            # Send hello
            await ws.send(json.dumps(SAMPLE_HELLO))
            # Send auth required
            await ws.send(json.dumps(SAMPLE_AUTH_REQUIRED))

            async for raw in ws:
                msg = json.loads(raw)
                if msg["type"] == "auth":
                    if self.auth_success:
                        await ws.send(json.dumps(SAMPLE_AUTH_SUCCESS))
                        if self.send_partial:
                            partial_status = dict(SAMPLE_FULL_STATUS)
                            partial_status["partial"] = True
                            partial_status["status"] = {"alw": True, "amp": 16}
                            await ws.send(json.dumps(partial_status))
                            full = dict(SAMPLE_FULL_STATUS)
                            full["partial"] = False
                            await ws.send(json.dumps(full))
                        else:
                            await ws.send(json.dumps(SAMPLE_FULL_STATUS))
                    else:
                        await ws.send(
                            json.dumps(
                                {
                                    "type": "authError",
                                    "message": "Wrong password",
                                }
                            )
                        )
                elif msg["type"] == "setValue":
                    await ws.send(
                        json.dumps(
                            {
                                "type": "response",
                                "requestId": msg["requestId"],
                                "success": True,
                                "status": {msg["key"]: msg["value"]},
                            }
                        )
                    )
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
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self._connections.remove(ws)


@pytest.fixture
async def mock_server() -> AsyncGenerator[MockWattpilotServer, None]:
    server = MockWattpilotServer()
    await server.start()
    yield server
    await server.stop()


@pytest.fixture
async def wattpilot_client(mock_server: MockWattpilotServer) -> AsyncGenerator[Wattpilot, None]:
    """A connected Wattpilot client against the mock server."""
    wp = Wattpilot(
        host=f"127.0.0.1:{mock_server.port}",
        password=SAMPLE_PASSWORD,
        serial=SAMPLE_SERIAL,
        connect_timeout=5.0,
        init_timeout=5.0,
    )
    # Override URL to use the dynamic port
    wp._url = f"ws://127.0.0.1:{mock_server.port}/ws"
    await wp.connect()
    yield wp
    await wp.disconnect()


@pytest.fixture
def sample_api_def() -> ApiDefinition:
    """Pre-loaded API definition from the real YAML."""
    return load_api_definition(split_properties=True)


@pytest.fixture
def sample_full_status() -> dict[str, Any]:
    return dict(SAMPLE_FULL_STATUS)

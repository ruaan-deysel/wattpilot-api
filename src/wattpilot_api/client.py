"""Async WebSocket client for Fronius Wattpilot devices."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import json
import logging
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import websockets
import websockets.asyncio.client

from wattpilot_api.auth import (
    compute_auth_response,
    generate_token,
    hash_password,
    sign_secured_message,
)
from wattpilot_api.exceptions import (
    AuthenticationError,
    ConnectionError,
)
from wattpilot_api.models import AuthHashType, DeviceInfo, LoadMode

_LOGGER = logging.getLogger(__name__)

WPFLEX_DEVICE_TYPE = "wattpilot_flex"

type PropertyCallback = Callable[[str, Any], Any]
type MessageCallback = Callable[[dict[str, Any]], Any]


class Wattpilot:
    """Async client for a Fronius Wattpilot wallbox.

    Usage::

        async with Wattpilot("192.168.1.100", "mypassword") as wp:
            print(wp.power)
            await wp.set_power(16)
    """

    def __init__(
        self,
        host: str,
        password: str,
        serial: str | None = None,
        *,
        cloud: bool = False,
        connect_timeout: float = 30.0,
        init_timeout: float = 30.0,
    ) -> None:
        self._host = host
        self._password = password
        self._cloud = cloud
        self._connect_timeout = connect_timeout
        self._init_timeout = init_timeout

        self._device = DeviceInfo(serial=serial or "")
        self._hashed_password: bytes = b""
        self._auth_hash_type = AuthHashType.PBKDF2

        if cloud:
            self._url = f"wss://app.wattpilot.io/app/{serial or ''}?version=1.2.9"
        else:
            self._url = f"ws://{host}/ws"

        self._ws: websockets.asyncio.client.ClientConnection | None = None
        self._message_loop_task: asyncio.Task[None] | None = None
        self._request_id = 0
        self._connected = False
        self._all_props: dict[str, Any] = {}
        self._all_props_initialized = False

        self._connected_event = asyncio.Event()
        self._initialized_event = asyncio.Event()
        self._auth_error: AuthenticationError | None = None

        # Named property caches
        self._voltage1: float | None = None
        self._voltage2: float | None = None
        self._voltage3: float | None = None
        self._voltage_n: float | None = None
        self._amps1: float | None = None
        self._amps2: float | None = None
        self._amps3: float | None = None
        self._power1: float | None = None
        self._power2: float | None = None
        self._power3: float | None = None
        self._power_n: float | None = None
        self._power: float | None = None
        self._amp: int | None = None
        self._version: str | None = None
        self._firmware: str | None = None
        self._wifi_ssid: str | None = None
        self._mode: int | None = None
        self._car_connected: int | None = None
        self._allow_charging: bool | None = None
        self._access_state: int | None = None
        self._cable_type: int | None = None
        self._cable_lock: int | None = None
        self._frequency: float | None = None
        self._phases: Any = None
        self._energy_counter_since_start: float | None = None
        self._energy_counter_total: float | None = None
        self._error_state: int | None = None
        self._cae: bool | None = None
        self._cak: str | None = None

        # Callbacks
        self._property_callbacks: list[PropertyCallback] = []
        self._message_callbacks: list[MessageCallback] = []

        # Pre-hash password if serial is already known
        if serial:
            self._update_hashed_password()

    # ---- Context manager ----

    async def __aenter__(self) -> Wattpilot:
        await self.connect()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.disconnect()

    # ---- Connection lifecycle ----

    async def connect(self) -> None:
        """Open the WebSocket and authenticate."""
        if self._connected:
            return

        self._connected_event.clear()
        self._initialized_event.clear()
        self._auth_error = None

        self._ws = await websockets.asyncio.client.connect(self._url)
        self._message_loop_task = asyncio.create_task(self._message_loop())

        try:
            await asyncio.wait_for(self._connected_event.wait(), self._connect_timeout)
        except TimeoutError as exc:
            await self.disconnect()
            msg = "Timeout waiting for authentication"
            raise ConnectionError(msg) from exc

        if self._auth_error is not None:
            err = self._auth_error
            await self.disconnect()
            raise err

        try:
            await asyncio.wait_for(self._initialized_event.wait(), self._init_timeout)
        except TimeoutError as exc:
            await self.disconnect()
            msg = "Timeout waiting for property initialization"
            raise ConnectionError(msg) from exc

        _LOGGER.info("Connected to Wattpilot %s", self._device.serial)

    async def disconnect(self) -> None:
        """Close the WebSocket connection."""
        if self._message_loop_task is not None:
            self._message_loop_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._message_loop_task
            self._message_loop_task = None

        if self._ws is not None:
            await self._ws.close()
            self._ws = None

        self._connected = False
        self._connected_event.clear()
        self._initialized_event.clear()

    # ---- Read-only properties ----

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def serial(self) -> str:
        return self._device.serial

    @property
    def name(self) -> str:
        return self._device.name

    @property
    def hostname(self) -> str:
        return self._device.hostname

    @property
    def manufacturer(self) -> str:
        return self._device.manufacturer

    @property
    def device_type(self) -> str:
        return self._device.device_type

    @property
    def protocol(self) -> int:
        return self._device.protocol

    @property
    def secured(self) -> int:
        return self._device.secured

    @property
    def version(self) -> str | None:
        return self._version or self._device.version or None

    @property
    def firmware(self) -> str | None:
        return self._firmware

    @property
    def voltage1(self) -> float | None:
        return self._voltage1

    @property
    def voltage2(self) -> float | None:
        return self._voltage2

    @property
    def voltage3(self) -> float | None:
        return self._voltage3

    @property
    def voltage_n(self) -> float | None:
        return self._voltage_n

    @property
    def amps1(self) -> float | None:
        return self._amps1

    @property
    def amps2(self) -> float | None:
        return self._amps2

    @property
    def amps3(self) -> float | None:
        return self._amps3

    @property
    def power1(self) -> float | None:
        return self._power1

    @property
    def power2(self) -> float | None:
        return self._power2

    @property
    def power3(self) -> float | None:
        return self._power3

    @property
    def power_n(self) -> float | None:
        return self._power_n

    @property
    def power(self) -> float | None:
        return self._power

    @property
    def amp(self) -> int | None:
        return self._amp

    @property
    def mode(self) -> int | None:
        return self._mode

    @property
    def car_connected(self) -> int | None:
        return self._car_connected

    @property
    def allow_charging(self) -> bool | None:
        return self._allow_charging

    @property
    def access_state(self) -> int | None:
        return self._access_state

    @property
    def cable_type(self) -> int | None:
        return self._cable_type

    @property
    def cable_lock(self) -> int | None:
        return self._cable_lock

    @property
    def frequency(self) -> float | None:
        return self._frequency

    @property
    def phases(self) -> Any:
        return self._phases

    @property
    def energy_counter_since_start(self) -> float | None:
        return self._energy_counter_since_start

    @property
    def energy_counter_total(self) -> float | None:
        return self._energy_counter_total

    @property
    def error_state(self) -> int | None:
        return self._error_state

    @property
    def wifi_ssid(self) -> str | None:
        return self._wifi_ssid

    @property
    def cae(self) -> bool | None:
        return self._cae

    @property
    def cak(self) -> str | None:
        return self._cak

    @property
    def all_properties(self) -> dict[str, Any]:
        return dict(self._all_props)

    @property
    def properties_initialized(self) -> bool:
        return self._all_props_initialized

    # ---- Commands ----

    async def set_property(self, name: str, value: Any) -> None:
        """Set a single property on the device."""
        self._request_id += 1
        message: dict[str, Any] = {
            "type": "setValue",
            "requestId": self._request_id,
            "key": name,
            "value": value,
        }
        secure = self._device.secured is not None and self._device.secured > 0
        await self._send(message, secure=secure)

    async def set_power(self, amperage: int) -> None:
        """Set the charging amperage."""
        await self.set_property("amp", amperage)

    async def set_mode(self, mode: LoadMode) -> None:
        """Set the load mode."""
        await self.set_property("lmo", int(mode))

    # ---- Callbacks ----

    def on_property_change(self, callback: PropertyCallback) -> Callable[[], None]:
        """Register a property-change callback. Returns an unsubscribe function."""
        self._property_callbacks.append(callback)

        def unsubscribe() -> None:
            self._property_callbacks.remove(callback)

        return unsubscribe

    def on_message(self, callback: MessageCallback) -> Callable[[], None]:
        """Register a raw-message callback. Returns an unsubscribe function."""
        self._message_callbacks.append(callback)

        def unsubscribe() -> None:
            self._message_callbacks.remove(callback)

        return unsubscribe

    # ---- Internal: message loop ----

    async def _message_loop(self) -> None:
        assert self._ws is not None
        try:
            async for raw in self._ws:
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                await self._handle_message(raw)
        except websockets.exceptions.ConnectionClosed:  # pragma: no cover
            _LOGGER.info("WebSocket connection closed")
        finally:
            self._connected = False
            self._connected_event.clear()

    async def _handle_message(self, raw: str) -> None:
        _LOGGER.debug("Message received: %s", raw)
        msg = json.loads(raw)

        # Fire raw message callbacks
        for cb in self._message_callbacks:
            if inspect.iscoroutinefunction(cb):
                await cb(msg)
            else:
                cb(msg)

        msg_type = msg.get("type", "")
        ns = json.loads(raw, object_hook=lambda d: SimpleNamespace(**d))

        match msg_type:
            case "hello":
                self._on_hello(ns)
            case "authRequired":
                await self._on_auth_required(ns)
            case "authSuccess":
                self._on_auth_success(ns)
            case "authError":
                self._on_auth_error(ns)
            case "fullStatus":
                self._on_full_status(ns)
            case "deltaStatus":
                self._on_delta_status(ns)
            case "response":
                self._on_response(ns)
            case "clearInverters" | "updateInverter":
                pass
            case _:
                _LOGGER.debug("Unhandled message type: %s", msg_type)

    def _on_hello(self, msg: SimpleNamespace) -> None:
        _LOGGER.info("Connected to Wattpilot serial %s", msg.serial)
        self._device.serial = msg.serial
        if hasattr(msg, "hostname"):
            self._device.name = msg.hostname
            self._device.hostname = msg.hostname
        if hasattr(msg, "friendly_name"):
            self._device.friendly_name = msg.friendly_name
        if hasattr(msg, "version"):
            self._device.version = msg.version
        self._device.manufacturer = getattr(msg, "manufacturer", "")
        self._device.device_type = getattr(msg, "devicetype", "")
        self._device.protocol = getattr(msg, "protocol", 0)
        if hasattr(msg, "secured"):
            self._device.secured = msg.secured

    async def _on_auth_required(self, msg: SimpleNamespace) -> None:
        if hasattr(msg, "hash"):
            self._auth_hash_type = AuthHashType(msg.hash)
        elif self._device.device_type == WPFLEX_DEVICE_TYPE:
            self._auth_hash_type = AuthHashType.BCRYPT

        self._update_hashed_password()

        token3 = generate_token()
        auth_hash = compute_auth_response(msg.token1, msg.token2, token3, self._hashed_password)
        response = {"type": "auth", "token3": token3, "hash": auth_hash}
        await self._send(response)

    def _on_auth_success(self, msg: SimpleNamespace) -> None:
        self._connected = True
        self._connected_event.set()
        _LOGGER.info("Authentication successful")

    def _on_auth_error(self, msg: SimpleNamespace) -> None:
        error_msg = getattr(msg, "message", "Unknown auth error")
        _LOGGER.error("Authentication failed: %s", error_msg)
        self._auth_error = AuthenticationError(error_msg)
        self._connected_event.set()  # Unblock connect() so it can check _auth_error

    def _on_full_status(self, msg: SimpleNamespace) -> None:
        props = msg.status.__dict__
        for key, value in props.items():
            self._update_property(key, value)
        if hasattr(msg, "partial") and not self._all_props_initialized:
            if not msg.partial:
                self._all_props_initialized = True
                self._initialized_event.set()
        else:
            self._all_props_initialized = True
            self._initialized_event.set()

    def _on_delta_status(self, msg: SimpleNamespace) -> None:
        if not self._all_props_initialized:
            self._all_props_initialized = True
            self._initialized_event.set()
        props = msg.status.__dict__
        for key, value in props.items():
            self._update_property(key, value)

    def _on_response(self, msg: SimpleNamespace) -> None:
        if msg.success:
            props = msg.status.__dict__
            for key, value in props.items():
                self._update_property(key, value)
        else:
            _LOGGER.error(
                "Command failed (requestId=%s): %s",
                msg.requestId,
                getattr(msg, "message", "unknown"),
            )

    def _update_property(self, name: str, value: Any) -> None:
        self._all_props[name] = value

        match name:
            case "acs":
                self._access_state = value
            case "cbl":
                self._cable_type = value
            case "fhz":
                self._frequency = value
            case "pha":
                self._phases = value
            case "wh":
                self._energy_counter_since_start = value
            case "err":
                self._error_state = value
            case "ust":
                self._cable_lock = value
            case "eto":
                self._energy_counter_total = value
            case "cae":
                self._cae = value
            case "cak":
                self._cak = value
            case "lmo":
                self._mode = value
            case "car":
                self._car_connected = value
            case "alw":
                self._allow_charging = value
            case "nrg":
                self._voltage1 = value[0]
                self._voltage2 = value[1]
                self._voltage3 = value[2]
                self._voltage_n = value[3]
                self._amps1 = value[4]
                self._amps2 = value[5]
                self._amps3 = value[6]
                self._power1 = value[7] * 0.001
                self._power2 = value[8] * 0.001
                self._power3 = value[9] * 0.001
                self._power_n = value[10] * 0.001
                self._power = value[11] * 0.001
            case "amp":
                self._amp = value
            case "version":
                self._version = value
            case "ast":
                self._access_state = value
            case "fwv":
                self._firmware = value
            case "wss":
                self._wifi_ssid = value

        # Fire property callbacks
        for cb in self._property_callbacks:
            if inspect.iscoroutinefunction(cb):
                task = asyncio.ensure_future(cb(name, value))
                task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
            else:
                cb(name, value)

    def _update_hashed_password(self) -> None:
        if not self._password or not self._device.serial:
            return
        self._hashed_password = hash_password(
            self._password, self._device.serial, self._auth_hash_type
        )

    async def _send(self, message: dict[str, Any], *, secure: bool = False) -> None:
        if self._ws is None:
            msg = "Not connected"
            raise ConnectionError(msg)

        if secure:
            message = sign_secured_message(message, self._hashed_password)

        _LOGGER.debug("Sending: %s", json.dumps(message))
        await self._ws.send(json.dumps(message))

    def __str__(self) -> str:
        if not self.connected:
            return "Not connected"
        lines = [
            f"Wattpilot: {self.name}",
            f"Serial: {self.serial}",
            f"Connected: {self.connected}",
            f"Car Connected: {self.car_connected}",
            f"Charge Status: {self.allow_charging}",
            f"Mode: {self.mode}",
            f"Power: {self.amp}",
        ]
        if self.power is not None:
            lines.append(
                f"Charge: {self.power:.2f}kW -- "
                f"{self.voltage1}V/{self.voltage2}V/{self.voltage3}V -- "
                f"{self.amps1:.2f}A/{self.amps2:.2f}A/{self.amps3:.2f}A -- "
                f"{self.power1:.2f}kW/{self.power2:.2f}kW/{self.power3:.2f}kW"
            )
        return "\n".join(lines)

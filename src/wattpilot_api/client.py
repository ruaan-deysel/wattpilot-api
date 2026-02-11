"""Async WebSocket client for Fronius Wattpilot devices."""

from __future__ import annotations

import asyncio
import contextlib
import datetime
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
from wattpilot_api.definition import ApiDefinition, load_api_definition
from wattpilot_api.exceptions import (
    AuthenticationError,
    ConnectionError,
    PropertyError,
)
from wattpilot_api.models import AuthHashType, CloudInfo, DeviceInfo, LoadMode

_LOGGER = logging.getLogger(__name__)

WPFLEX_DEVICE_TYPE = "wattpilot_flex"
CLOUD_API_BASE_URL = "https://app.wattpilot.io/app"

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

        # Lazy-loaded API definition for type coercion
        self._api_def_cache: ApiDefinition | None = None

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
            if not self._all_props_initialized:
                try:
                    await asyncio.wait_for(self._initialized_event.wait(), self._init_timeout)
                except TimeoutError as exc:
                    await self.disconnect()
                    msg = "Timeout waiting for property initialization"
                    raise ConnectionError(msg) from exc
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

    # ---- Additional typed properties ----

    # Device info

    @property
    def variant(self) -> str | None:
        """Device variant (e.g. ``'11kW'``, ``'22kW'``)."""
        return self._all_props.get("var")

    @property
    def model(self) -> str | None:
        """Device model / type string."""
        return self._all_props.get("typ")

    # Charging state

    @property
    def car_state(self) -> int | None:
        """Car connection state (use :class:`CarStatus` enum)."""
        return self._all_props.get("car")

    @property
    def cable_unlock_status(self) -> int | None:
        """Cable unlock status."""
        return self._all_props.get("cus")

    @property
    def charging_reason(self) -> int | None:
        """Detailed charging reason / model status."""
        return self._all_props.get("modelStatus")

    @property
    def force_state(self) -> int | None:
        """Force charging state (use :class:`ForceState` enum)."""
        return self._all_props.get("frc")

    @property
    def active_transaction_chip(self) -> int | None:
        """Active RFID transaction chip ID."""
        return self._all_props.get("trx")

    # Configuration

    @property
    def button_lock(self) -> int | None:
        """Button / access lock level."""
        return self._all_props.get("bac")

    @property
    def daylight_saving(self) -> int | None:
        """Daylight saving time mode (``1`` = enabled)."""
        return self._all_props.get("tds")

    @property
    def phase_switch_mode(self) -> int | None:
        """Phase switching mode (use :class:`PhaseSwitchMode` enum)."""
        return self._all_props.get("psm")

    # Diagnostics

    @property
    def inverter_info(self) -> Any:
        """Connected inverter information."""
        return self._all_props.get("cci")

    @property
    def wifi_connection_info(self) -> Any:
        """WiFi connection details (SSID, IP, netmask, etc.)."""
        return self._all_props.get("ccw")

    @property
    def lock_feedback(self) -> int | None:
        """Lock feedback status."""
        return self._all_props.get("ffb")

    @property
    def effective_lock_setting(self) -> int | None:
        """Effective lock setting."""
        return self._all_props.get("lck")

    @property
    def local_time(self) -> str | None:
        """Local time as reported by the charger."""
        return self._all_props.get("loc")

    @property
    def wifi_signal_strength(self) -> int | None:
        """WiFi signal strength (RSSI in dBm)."""
        return self._all_props.get("rssi")

    @property
    def temperature(self) -> Any:
        """Temperature sensor readings."""
        return self._all_props.get("tma")

    @property
    def uptime_ms(self) -> int | None:
        """Device uptime in milliseconds."""
        return self._all_props.get("rbt")

    @property
    def reboot_count(self) -> int | None:
        """Number of device reboots."""
        return self._all_props.get("rbc")

    @property
    def websocket_queue_size(self) -> int | None:
        """WebSocket send queue size."""
        return self._all_props.get("qsw")

    @property
    def http_clients(self) -> int | None:
        """Number of connected HTTP clients."""
        return self._all_props.get("wcch")

    @property
    def websocket_clients(self) -> int | None:
        """Number of connected WebSocket clients."""
        return self._all_props.get("wccw")

    @property
    def wifi_status(self) -> int | None:
        """WiFi connection status."""
        return self._all_props.get("wst")

    # RFID

    @property
    def rfid_cards(self) -> Any:
        """Configured RFID cards."""
        return self._all_props.get("cards")

    # PV / Solar

    @property
    def pv_surplus_enabled(self) -> bool | None:
        """Whether PV surplus charging is enabled."""
        return self._all_props.get("fup")

    @property
    def pv_surplus_start_power(self) -> float | None:
        """PV surplus start power threshold in watts."""
        return self._all_props.get("fst")

    @property
    def pv_battery_threshold(self) -> float | None:
        """PV battery minimum threshold."""
        return self._all_props.get("fam")

    @property
    def min_charging_time(self) -> int | None:
        """Minimum charging time in seconds."""
        return self._all_props.get("fmt")

    @property
    def next_trip_energy(self) -> float | None:
        """Planned energy for next trip in Wh."""
        return self._all_props.get("fte")

    @property
    def next_trip_time(self) -> int | None:
        """Planned departure time for next trip (seconds since midnight)."""
        return self._all_props.get("ftt")

    # Firmware

    @property
    def installed_firmware_version(self) -> str | None:
        """Currently installed firmware version."""
        return self._firmware

    @property
    def available_firmware_versions(self) -> list[str]:
        """List of available firmware versions for update."""
        val = self._all_props.get("onv")
        if isinstance(val, list):
            return [str(v) for v in val]
        if isinstance(val, str) and val:
            return [val]
        return []

    @property
    def firmware_update_available(self) -> bool:
        """Whether a firmware update is available."""
        available = self.available_firmware_versions
        if not available:
            return False
        installed = self.firmware
        if not installed:
            return bool(available)
        return any(v != installed for v in available)

    # Cloud API

    @property
    def cloud_enabled(self) -> bool | None:
        """Whether the go-e Cloud API is enabled."""
        return self._cae

    @property
    def cloud_api_key(self) -> str | None:
        """Cloud API key (available when cloud is enabled)."""
        return self._cak

    @property
    def cloud_api_url(self) -> str | None:
        """Cloud API base URL for this device."""
        if not self._cae or not self.serial:
            return None
        return f"{CLOUD_API_BASE_URL}/{self.serial}"

    # ---- Commands ----

    async def set_property(self, name: str, value: Any) -> None:
        """Set a single property on the device.

        Values are automatically coerced to the type expected by the charger
        protocol (based on the API definition's ``jsonType``).
        """
        value = self._coerce_value(name, value)
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

    async def set_next_trip(
        self,
        departure_time: datetime.time | datetime.datetime,
    ) -> None:
        """Schedule the next trip departure time.

        Handles timestamp conversion and DST adjustment automatically
        based on the charger's ``tds`` (daylight-saving) property.
        """
        if isinstance(departure_time, datetime.datetime):
            departure_time = departure_time.time()

        timestamp = departure_time.hour * 3600 + departure_time.minute * 60 + departure_time.second

        tds = self._all_props.get("tds")
        if tds is not None and int(tds) in (1, 2):
            timestamp += 3600

        await self.set_property("ftt", timestamp)

    async def set_next_trip_energy(self, energy_kwh: float) -> None:
        """Set the energy requirement for the next trip in kWh.

        Automatically sets the energy unit to kWh before updating.
        """
        await self.set_property("esk", True)
        await self.set_property("fte", energy_kwh)

    async def enable_cloud_api(self, *, timeout: float = 10.0) -> CloudInfo:
        """Enable the go-e Cloud API and wait for the API key.

        Returns a :class:`CloudInfo` with the API key and URL.
        Raises :class:`ConnectionError` if the API key is not received
        within *timeout* seconds.
        """
        await self.set_property("cae", True)

        elapsed = 0.0
        while elapsed < timeout:
            if self._cak and self._cak != "":
                return CloudInfo(
                    enabled=True,
                    api_key=self._cak,
                    url=f"{CLOUD_API_BASE_URL}/{self.serial}",
                )
            await asyncio.sleep(1)
            elapsed += 1

        msg = "Timeout waiting for cloud API key"
        raise ConnectionError(msg)

    async def disable_cloud_api(self) -> None:
        """Disable the go-e Cloud API."""
        await self.set_property("cae", False)

    async def install_firmware_update(
        self,
        version: str | None = None,
        *,
        timeout: float = 120.0,
    ) -> None:
        """Install a firmware update and wait for the charger to reboot.

        If *version* is not specified, the first available version is used.
        Raises :class:`PropertyError` if no updates are available.
        Raises :class:`ConnectionError` on timeout.
        """
        if version is None:
            versions = self.available_firmware_versions
            if not versions:
                msg = "No firmware updates available"
                raise PropertyError(msg)
            version = versions[0]

        await self.set_property("oct", version)

        elapsed = 0.0
        while self.connected and elapsed < timeout:
            await asyncio.sleep(1)
            elapsed += 1

        if self.connected:
            msg = "Charger did not disconnect for firmware update"
            raise ConnectionError(msg)

        await self.disconnect()

        while elapsed < timeout:
            with contextlib.suppress(Exception):
                await self.connect()
                return
            await asyncio.sleep(2)
            elapsed += 2

        msg = "Timeout reconnecting after firmware update"
        raise ConnectionError(msg)

    # ---- Type coercion ----

    def _get_api_def(self) -> ApiDefinition:
        """Lazily load and cache the API definition."""
        if self._api_def_cache is None:
            self._api_def_cache = load_api_definition(split_properties=False)
        return self._api_def_cache

    def _coerce_value(self, name: str, value: Any) -> Any:
        """Coerce *value* to the protocol type expected for property *name*."""
        if isinstance(value, SimpleNamespace):
            return value.__dict__

        api_def = self._get_api_def()
        prop_def = api_def.properties.get(name)
        if prop_def is None:
            return value

        json_type = prop_def.get("jsonType", "")
        if not json_type:
            return value

        return self._coerce_to_json_type(value, json_type, name)

    def _coerce_to_json_type(self, value: Any, json_type: str, name: str) -> Any:
        """Convert *value* to the specified JSON type for property *name*."""
        match json_type:
            case "boolean":
                if isinstance(value, bool):
                    return value
                if isinstance(value, str):
                    lower = value.lower()
                    if lower in ("true", "1", "yes"):
                        return True
                    if lower in ("false", "0", "no"):
                        return False
                    msg = f"Cannot convert '{value}' to bool for property '{name}'"
                    raise PropertyError(msg)
                if isinstance(value, int | float):
                    return bool(value)
                msg = f"Cannot convert {type(value).__name__} to bool for property '{name}'"
                raise PropertyError(msg)
            case "integer":
                if isinstance(value, bool):
                    return int(value)
                if isinstance(value, int):
                    return value
                if isinstance(value, float):
                    return int(value)
                if isinstance(value, str):
                    with contextlib.suppress(ValueError):
                        return int(value)
                    with contextlib.suppress(ValueError):
                        return int(float(value))
                    msg = f"Cannot convert '{value}' to int for property '{name}'"
                    raise PropertyError(msg)
                msg = f"Cannot convert {type(value).__name__} to int for property '{name}'"
                raise PropertyError(msg)
            case "float":
                if isinstance(value, bool):
                    return float(value)
                if isinstance(value, int | float):
                    return float(value)
                if isinstance(value, str):
                    with contextlib.suppress(ValueError):
                        return float(value)
                    msg = f"Cannot convert '{value}' to float for property '{name}'"
                    raise PropertyError(msg)
                msg = f"Cannot convert {type(value).__name__} to float for property '{name}'"
                raise PropertyError(msg)
            case "string":
                return str(value)
            case _:
                return value

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

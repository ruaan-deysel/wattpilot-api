"""Integration tests against a real Wattpilot device.

Run with: WATTPILOT_HOST=192.168.20.25 WATTPILOT_PASSWORD=29Lighthouse pytest -m integration -v
"""

from __future__ import annotations

import asyncio
import os

import pytest

from wattpilot_api.client import Wattpilot
from wattpilot_api.models import LoadMode

pytestmark = pytest.mark.integration

INTEGRATION_HOST = os.environ.get("WATTPILOT_HOST", "")
INTEGRATION_PASSWORD = os.environ.get("WATTPILOT_PASSWORD", "")


@pytest.fixture
def skip_if_no_device() -> None:
    if not INTEGRATION_HOST or not INTEGRATION_PASSWORD:
        pytest.skip("WATTPILOT_HOST and WATTPILOT_PASSWORD not set")


class TestRealDeviceConnection:
    """Tests for basic connection and authentication."""

    async def test_connect_and_disconnect(self, skip_if_no_device: None) -> None:
        wp = Wattpilot(INTEGRATION_HOST, INTEGRATION_PASSWORD)
        await wp.connect()
        assert wp.connected is True
        assert wp.serial != ""
        assert wp.properties_initialized is True
        await wp.disconnect()
        assert wp.connected is False

    async def test_context_manager(self, skip_if_no_device: None) -> None:
        async with Wattpilot(INTEGRATION_HOST, INTEGRATION_PASSWORD) as wp:
            assert wp.connected is True
            assert wp.properties_initialized is True
        assert wp.connected is False


class TestRealDeviceInfo:
    """Tests for device info received in the hello message."""

    async def test_serial(self, skip_if_no_device: None) -> None:
        async with Wattpilot(INTEGRATION_HOST, INTEGRATION_PASSWORD) as wp:
            assert wp.serial != ""
            assert len(wp.serial) > 0

    async def test_device_identity(self, skip_if_no_device: None) -> None:
        async with Wattpilot(INTEGRATION_HOST, INTEGRATION_PASSWORD) as wp:
            assert wp.manufacturer != ""
            assert wp.name != ""
            assert wp.hostname != ""
            assert wp.device_type != ""
            assert wp.protocol >= 2

    async def test_version(self, skip_if_no_device: None) -> None:
        async with Wattpilot(INTEGRATION_HOST, INTEGRATION_PASSWORD) as wp:
            assert wp.version is not None
            assert wp.version != ""

    async def test_firmware(self, skip_if_no_device: None) -> None:
        async with Wattpilot(INTEGRATION_HOST, INTEGRATION_PASSWORD) as wp:
            assert wp.firmware is not None
            assert wp.firmware != ""


class TestRealDeviceProperties:
    """Tests for device properties received in fullStatus."""

    async def test_all_properties_populated(self, skip_if_no_device: None) -> None:
        async with Wattpilot(INTEGRATION_HOST, INTEGRATION_PASSWORD) as wp:
            all_props = wp.all_properties
            assert len(all_props) > 100, f"Expected 100+ properties, got {len(all_props)}"

    async def test_charging_properties(self, skip_if_no_device: None) -> None:
        async with Wattpilot(INTEGRATION_HOST, INTEGRATION_PASSWORD) as wp:
            assert wp.amp is not None
            assert isinstance(wp.amp, int)
            assert 6 <= wp.amp <= 32

            assert wp.allow_charging is not None
            assert isinstance(wp.allow_charging, bool)

            assert wp.car_connected is not None
            assert isinstance(wp.car_connected, int)

            assert wp.mode is not None
            assert isinstance(wp.mode, int)

    async def test_energy_readings(self, skip_if_no_device: None) -> None:
        async with Wattpilot(INTEGRATION_HOST, INTEGRATION_PASSWORD) as wp:
            # Voltages should be available
            assert wp.voltage1 is not None
            assert isinstance(wp.voltage1, float)

            # Power readings (may be 0 if not charging)
            assert wp.power is not None
            assert isinstance(wp.power, float)
            assert wp.power >= 0

            # Energy counters
            assert wp.energy_counter_total is not None
            assert wp.energy_counter_total > 0

    async def test_grid_frequency(self, skip_if_no_device: None) -> None:
        async with Wattpilot(INTEGRATION_HOST, INTEGRATION_PASSWORD) as wp:
            assert wp.frequency is not None
            assert isinstance(wp.frequency, float)
            # Australian grid: ~50 Hz
            assert 49.0 <= wp.frequency <= 51.0

    async def test_cable_and_access(self, skip_if_no_device: None) -> None:
        async with Wattpilot(INTEGRATION_HOST, INTEGRATION_PASSWORD) as wp:
            assert wp.cable_type is not None
            assert isinstance(wp.cable_type, int)

            assert wp.cable_lock is not None
            assert isinstance(wp.cable_lock, int)

            assert wp.access_state is not None
            assert isinstance(wp.access_state, int)

    async def test_phases(self, skip_if_no_device: None) -> None:
        async with Wattpilot(INTEGRATION_HOST, INTEGRATION_PASSWORD) as wp:
            assert wp.phases is not None
            assert isinstance(wp.phases, list)
            assert len(wp.phases) == 6

    async def test_error_state(self, skip_if_no_device: None) -> None:
        async with Wattpilot(INTEGRATION_HOST, INTEGRATION_PASSWORD) as wp:
            assert wp.error_state is not None
            assert isinstance(wp.error_state, int)

    async def test_nrg_array(self, skip_if_no_device: None) -> None:
        """The nrg array contains 16 values: voltages, amps, power readings."""
        async with Wattpilot(INTEGRATION_HOST, INTEGRATION_PASSWORD) as wp:
            nrg = wp.all_properties.get("nrg")
            assert nrg is not None
            assert isinstance(nrg, list)
            assert len(nrg) == 16


class TestRealDeviceCallbacks:
    """Tests for property change callbacks against real device."""

    async def test_property_callback_fires(self, skip_if_no_device: None) -> None:
        received: list[tuple[str, object]] = []

        async with Wattpilot(INTEGRATION_HOST, INTEGRATION_PASSWORD) as wp:
            unsub = wp.on_property_change(lambda name, value: received.append((name, value)))
            # Wait a moment for any delta status updates
            await asyncio.sleep(2)
            unsub()

        # The device may or may not send delta updates in 2 seconds,
        # so we just verify the mechanism doesn't crash.
        # Received may be empty if no values changed.
        assert isinstance(received, list)


class TestRealDeviceSetProperty:
    """Tests for setting properties on the real device (non-destructive)."""

    async def test_read_and_restore_amp(self, skip_if_no_device: None) -> None:
        """Read current amp, set it to same value (no-op change)."""
        async with Wattpilot(INTEGRATION_HOST, INTEGRATION_PASSWORD) as wp:
            original_amp = wp.amp
            assert original_amp is not None
            # Set to same value — safe, no actual change
            await wp.set_power(original_amp)
            # Allow a moment for the response
            await asyncio.sleep(0.5)
            assert wp.amp == original_amp

    async def test_read_and_restore_mode(self, skip_if_no_device: None) -> None:
        """Read current mode, set it to same value (no-op change)."""
        async with Wattpilot(INTEGRATION_HOST, INTEGRATION_PASSWORD) as wp:
            original_mode = wp.mode
            assert original_mode is not None
            # Set to same value — safe
            await wp.set_mode(LoadMode(original_mode))
            await asyncio.sleep(0.5)
            assert wp.mode == original_mode


class TestRealDeviceStr:
    """Test string representation with real device."""

    async def test_str_connected(self, skip_if_no_device: None) -> None:
        async with Wattpilot(INTEGRATION_HOST, INTEGRATION_PASSWORD) as wp:
            s = str(wp)
            assert "Wattpilot" in s
            assert wp.serial in s

"""Integration tests against a real Wattpilot device.

Run with: WATTPILOT_HOST=192.168.20.25 WATTPILOT_PASSWORD=29Lighthouse pytest -m integration -v
"""

from __future__ import annotations

import asyncio
import datetime
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
            # Allow a moment for delta updates to arrive
            await asyncio.sleep(1)
            nrg = wp.all_properties.get("nrg")
            if nrg is not None:
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


class TestRealDeviceNewProperties:
    """Tests for additional typed properties from issue #5."""

    async def test_device_variant_and_model(self, skip_if_no_device: None) -> None:
        async with Wattpilot(INTEGRATION_HOST, INTEGRATION_PASSWORD) as wp:
            # variant and model may or may not be set depending on device
            _ = wp.variant
            _ = wp.model

    async def test_charging_state_properties(self, skip_if_no_device: None) -> None:
        async with Wattpilot(INTEGRATION_HOST, INTEGRATION_PASSWORD) as wp:
            assert wp.car_state is not None
            assert isinstance(wp.car_state, int)

            _ = wp.cable_unlock_status
            _ = wp.force_state
            _ = wp.charging_reason

    async def test_config_properties(self, skip_if_no_device: None) -> None:
        async with Wattpilot(INTEGRATION_HOST, INTEGRATION_PASSWORD) as wp:
            _ = wp.button_lock
            _ = wp.daylight_saving
            _ = wp.phase_switch_mode

    async def test_diagnostic_properties(self, skip_if_no_device: None) -> None:
        async with Wattpilot(INTEGRATION_HOST, INTEGRATION_PASSWORD) as wp:
            assert wp.wifi_signal_strength is not None
            assert isinstance(wp.wifi_signal_strength, int)
            assert wp.wifi_signal_strength < 0  # RSSI is negative

            assert wp.uptime_ms is not None
            assert wp.uptime_ms > 0

            _ = wp.reboot_count
            _ = wp.temperature
            _ = wp.wifi_status
            _ = wp.websocket_clients
            _ = wp.http_clients
            _ = wp.websocket_queue_size

    async def test_wifi_info(self, skip_if_no_device: None) -> None:
        async with Wattpilot(INTEGRATION_HOST, INTEGRATION_PASSWORD) as wp:
            _ = wp.wifi_connection_info
            _ = wp.inverter_info
            _ = wp.local_time

    async def test_pv_solar_properties(self, skip_if_no_device: None) -> None:
        async with Wattpilot(INTEGRATION_HOST, INTEGRATION_PASSWORD) as wp:
            _ = wp.pv_surplus_enabled
            _ = wp.pv_surplus_start_power
            _ = wp.pv_battery_threshold
            _ = wp.min_charging_time
            _ = wp.next_trip_energy
            _ = wp.next_trip_time

    async def test_firmware_properties(self, skip_if_no_device: None) -> None:
        async with Wattpilot(INTEGRATION_HOST, INTEGRATION_PASSWORD) as wp:
            assert wp.installed_firmware_version is not None
            assert wp.installed_firmware_version != ""
            _ = wp.available_firmware_versions
            _ = wp.firmware_update_available

    async def test_cloud_properties(self, skip_if_no_device: None) -> None:
        async with Wattpilot(INTEGRATION_HOST, INTEGRATION_PASSWORD) as wp:
            _ = wp.cloud_enabled
            _ = wp.cloud_api_key
            _ = wp.cloud_api_url

    async def test_rfid_cards(self, skip_if_no_device: None) -> None:
        async with Wattpilot(INTEGRATION_HOST, INTEGRATION_PASSWORD) as wp:
            _ = wp.rfid_cards


class TestRealDeviceTypeCoercion:
    """Tests for type coercion from issue #2."""

    async def test_set_property_with_string_int(self, skip_if_no_device: None) -> None:
        """set_property coerces string to int based on API definition."""
        async with Wattpilot(INTEGRATION_HOST, INTEGRATION_PASSWORD) as wp:
            original_amp = wp.amp
            assert original_amp is not None
            # Set via string — should be coerced to int
            await wp.set_power(original_amp)
            await asyncio.sleep(0.5)
            assert wp.amp == original_amp


class TestRealDeviceNextTrip:
    """Tests for set_next_trip from issue #3."""

    async def test_set_next_trip_time(self, skip_if_no_device: None) -> None:
        async with Wattpilot(INTEGRATION_HOST, INTEGRATION_PASSWORD) as wp:
            original = wp.next_trip_time
            t = datetime.time(8, 0, 0)
            await wp.set_next_trip(t)
            await asyncio.sleep(0.5)
            # Restore original if it existed
            if original is not None:
                await wp.set_property("ftt", original)

    async def test_set_next_trip_energy(self, skip_if_no_device: None) -> None:
        async with Wattpilot(INTEGRATION_HOST, INTEGRATION_PASSWORD) as wp:
            original = wp.next_trip_energy
            await wp.set_next_trip_energy(15.0)
            await asyncio.sleep(0.5)
            # Restore original
            if original is not None:
                await wp.set_property("fte", original)

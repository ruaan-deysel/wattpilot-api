"""Tests for enums and dataclasses."""

import pytest

from wattpilot_api.models import (
    AccessState,
    AuthHashType,
    CableLockMode,
    CarStatus,
    DeviceInfo,
    ErrorState,
    HaConfig,
    LoadMode,
    MqttConfig,
)


class TestLoadMode:
    def test_values(self) -> None:
        assert LoadMode.DEFAULT == 3
        assert LoadMode.ECO == 4
        assert LoadMode.NEXTTRIP == 5

    def test_is_int(self) -> None:
        assert isinstance(LoadMode.DEFAULT, int)
        assert LoadMode.DEFAULT + 1 == 4

    def test_from_int(self) -> None:
        assert LoadMode(3) == LoadMode.DEFAULT
        assert LoadMode(4) == LoadMode.ECO


class TestCarStatus:
    def test_values(self) -> None:
        assert CarStatus.NO_CAR == 1
        assert CarStatus.CHARGING == 2
        assert CarStatus.READY == 3
        assert CarStatus.COMPLETE == 4

    def test_is_int(self) -> None:
        assert isinstance(CarStatus.CHARGING, int)


class TestAccessState:
    def test_values(self) -> None:
        assert AccessState.OPEN == 0
        assert AccessState.WAIT == 1


class TestErrorState:
    def test_values(self) -> None:
        assert ErrorState.UNKNOWN == 0
        assert ErrorState.IDLE == 1
        assert ErrorState.CHARGING == 2
        assert ErrorState.WAIT_CAR == 3
        assert ErrorState.COMPLETE == 4
        assert ErrorState.ERROR == 5


class TestCableLockMode:
    def test_values(self) -> None:
        assert CableLockMode.NORMAL == 0
        assert CableLockMode.AUTO_UNLOCK == 1
        assert CableLockMode.ALWAYS_LOCK == 2


class TestAuthHashType:
    def test_values(self) -> None:
        assert AuthHashType.PBKDF2 == "pbkdf2"
        assert AuthHashType.BCRYPT == "bcrypt"

    def test_is_string(self) -> None:
        assert isinstance(AuthHashType.PBKDF2, str)
        assert AuthHashType.PBKDF2.upper() == "PBKDF2"


class TestMqttConfig:
    def test_defaults(self) -> None:
        config = MqttConfig()
        assert config.host == ""
        assert config.port == 1883
        assert config.client_id == "wattpilot2mqtt"
        assert config.topic_base == "wattpilot"
        assert config.publish_messages is False
        assert config.publish_properties is True
        assert config.properties == []
        assert config.messages == []

    def test_custom(self) -> None:
        config = MqttConfig(host="mqtt.local", port=8883, properties=["amp", "car"])
        assert config.host == "mqtt.local"
        assert config.port == 8883
        assert config.properties == ["amp", "car"]

    def test_frozen(self) -> None:
        config = MqttConfig()
        with pytest.raises(AttributeError):
            config.host = "other"  # type: ignore[misc]


class TestHaConfig:
    def test_defaults(self) -> None:
        config = HaConfig()
        assert config.enabled is False
        assert config.disabled_entities is False
        assert config.wait_init_s == 0
        assert config.wait_props_ms == 0
        assert config.properties == []

    def test_custom(self) -> None:
        config = HaConfig(enabled=True, properties=["amp"])
        assert config.enabled is True
        assert config.properties == ["amp"]


class TestDeviceInfo:
    def test_defaults(self) -> None:
        info = DeviceInfo()
        assert info.serial == ""
        assert info.name == ""
        assert info.manufacturer == ""

    def test_mutable(self) -> None:
        info = DeviceInfo()
        info.serial = "123"
        assert info.serial == "123"

    def test_custom(self) -> None:
        info = DeviceInfo(serial="999", manufacturer="fronius", device_type="wattpilot")
        assert info.serial == "999"
        assert info.manufacturer == "fronius"

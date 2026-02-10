"""Tests for the exception hierarchy."""

from wattpilot_api.exceptions import (
    AuthenticationError,
    CommandError,
    ConnectionError,
    PropertyError,
    WattpilotError,
)


class TestExceptionHierarchy:
    def test_base_exception(self) -> None:
        exc = WattpilotError("test")
        assert str(exc) == "test"
        assert isinstance(exc, Exception)

    def test_connection_error(self) -> None:
        exc = ConnectionError("connect failed")
        assert isinstance(exc, WattpilotError)
        assert isinstance(exc, Exception)
        assert str(exc) == "connect failed"

    def test_authentication_error(self) -> None:
        exc = AuthenticationError("bad password")
        assert isinstance(exc, WattpilotError)
        assert str(exc) == "bad password"

    def test_property_error(self) -> None:
        exc = PropertyError("unknown prop")
        assert isinstance(exc, WattpilotError)
        assert str(exc) == "unknown prop"

    def test_command_error(self) -> None:
        exc = CommandError("cmd failed")
        assert isinstance(exc, WattpilotError)
        assert str(exc) == "cmd failed"

    def test_catch_base_catches_all(self) -> None:
        for exc_cls in (ConnectionError, AuthenticationError, PropertyError, CommandError):
            try:
                raise exc_cls("test")
            except WattpilotError:
                pass  # Should be caught

    def test_empty_message(self) -> None:
        exc = WattpilotError()
        assert str(exc) == ""
        exc2 = ConnectionError()
        assert str(exc2) == ""

"""Exception hierarchy for the wattpilot-api library."""


class WattpilotError(Exception):
    """Base exception for all wattpilot-api errors."""


class ConnectionError(WattpilotError):
    """Raised when a connection to the Wattpilot device fails."""


class AuthenticationError(WattpilotError):
    """Raised when authentication with the Wattpilot device fails."""


class PropertyError(WattpilotError):
    """Raised when a property operation fails (unknown key, read-only, etc.)."""


class CommandError(WattpilotError):
    """Raised when a command sent to the Wattpilot device fails."""

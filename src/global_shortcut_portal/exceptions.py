"""Custom exception hierarchy for the Global Shortcut portal library."""


class PortalError(Exception):
    """Base exception for all portal-related errors."""


class PortalCallError(PortalError):
    """Raised when a D-Bus method call to the portal fails."""

    def __init__(self, message: str, dbus_error_name: str | None = None):
        self.dbus_error_name = dbus_error_name
        super().__init__(message)


class PortalResponseError(PortalError):
    """Raised when the portal returns a non-zero (failure) response code."""

    def __init__(self, response_code: int, message: str = ""):
        self.response_code = response_code
        msg = f"Portal response {response_code}"
        if message:
            msg += f": {message}"
        super().__init__(msg)


class SessionError(PortalError):
    """Raised when an operation is attempted on an invalid or uninitialised session."""

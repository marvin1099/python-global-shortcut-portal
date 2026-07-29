class PortalError(Exception):
    pass


class PortalCallError(PortalError):
    def __init__(self, message: str, dbus_error_name: str | None = None):
        self.dbus_error_name = dbus_error_name
        super().__init__(message)


class PortalResponseError(PortalError):
    def __init__(self, response_code: int, message: str = ""):
        self.response_code = response_code
        super().__init__(f"Portal response {response_code}: {message}")


class SessionError(PortalError):
    pass


class ShortcutError(PortalError):
    pass

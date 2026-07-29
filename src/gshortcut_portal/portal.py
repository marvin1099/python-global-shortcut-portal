from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from dbus_next import Message, MessageType, Variant
from dbus_next.aio import MessageBus

from gshortcut_portal.exceptions import PortalCallError, PortalResponseError

logger = logging.getLogger(__name__)

BUS_NAME = "org.freedesktop.portal.Desktop"
OBJECT_PATH = "/org/freedesktop/portal/desktop"
SHORTCUT_IFACE = "org.freedesktop.portal.GlobalShortcuts"
REQUEST_IFACE = "org.freedesktop.portal.Request"
REGISTRY_IFACE = "org.freedesktop.host.portal.Registry"


def _response_ok(code: int) -> bool:
    return code == 0


class Portal:
    def __init__(self) -> None:
        self._bus: MessageBus | None = None
        self._unique_name: str | None = None
        self._signal_handlers: dict[str, Callable] = {}
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        if self._connected:
            return
        self._bus = await MessageBus().connect()
        self._unique_name = self._bus.unique_name
        self._connected = True
        logger.info("Connected to session D-Bus as %s", self._unique_name)

    async def close(self) -> None:
        if self._bus:
            for handler in list(self._signal_handlers.values()):
                self._bus.remove_message_handler(handler)
            self._signal_handlers.clear()
            self._bus.disconnect()
        self._bus = None
        self._connected = False

    async def get_portal_version(self) -> int:
        msg = Message(
            destination=BUS_NAME,
            path=OBJECT_PATH,
            interface="org.freedesktop.DBus.Properties",
            member="Get",
            signature="ss",
            body=[SHORTCUT_IFACE, "version"],
        )
        reply = await self._call(msg)
        return reply.body[0].value

    async def register(self, app_id: str) -> None:
        msg = Message(
            destination=BUS_NAME,
            path=OBJECT_PATH,
            interface=REGISTRY_IFACE,
            member="Register",
            signature="sa{sv}",
            body=[app_id, {}],
        )
        await self._call(msg)
        logger.info("Registered app_id=%s with portal", app_id)

    async def create_session(
        self, handle_token: str, session_handle_token: str
    ) -> str:
        options = {
            "handle_token": Variant("s", handle_token),
            "session_handle_token": Variant("s", session_handle_token),
        }
        msg = Message(
            destination=BUS_NAME,
            path=OBJECT_PATH,
            interface=SHORTCUT_IFACE,
            member="CreateSession",
            signature="a{sv}",
            body=[options],
        )
        reply = await self._call(msg)
        request_path = reply.body[0]
        results = await self._await_response(request_path)
        return results["session_handle"]

    async def bind_shortcuts(
        self,
        session_handle: str,
        shortcuts: list[tuple[str, dict]],
        parent_window: str = "",
    ) -> list[tuple[str, dict]]:
        dbus_shortcuts = [
            (sid, self._to_variant_dict(opts)) for sid, opts in shortcuts
        ]
        options: dict[str, Variant] = {}
        msg = Message(
            destination=BUS_NAME,
            path=OBJECT_PATH,
            interface=SHORTCUT_IFACE,
            member="BindShortcuts",
            signature="oa(sa{sv})sa{sv}",
            body=[
                session_handle,
                dbus_shortcuts,
                parent_window,
                options,
            ],
        )
        reply = await self._call(msg)
        request_path = reply.body[0]
        result = await self._await_response(request_path)
        raw_list = result.get("shortcuts", [])
        return [
            (sid, self._from_variant_dict(opts))
            for sid, opts in raw_list
        ]

    async def list_shortcuts(
        self, session_handle: str
    ) -> list[tuple[str, dict]]:
        options: dict[str, Variant] = {}
        msg = Message(
            destination=BUS_NAME,
            path=OBJECT_PATH,
            interface=SHORTCUT_IFACE,
            member="ListShortcuts",
            signature="oa{sv}",
            body=[session_handle, options],
        )
        reply = await self._call(msg)
        request_path = reply.body[0]
        result = await self._await_response(request_path)
        raw_list = result.get("shortcuts", [])
        return [
            (sid, self._from_variant_dict(opts))
            for sid, opts in raw_list
        ]

    async def configure_shortcuts(
        self,
        session_handle: str,
        parent_window: str = "",
        activation_token: str | None = None,
    ) -> None:
        options: dict[str, Variant] = {}
        if activation_token:
            options["activation_token"] = Variant("s", activation_token)
        msg = Message(
            destination=BUS_NAME,
            path=OBJECT_PATH,
            interface=SHORTCUT_IFACE,
            member="ConfigureShortcuts",
            signature="osa{sv}",
            body=[session_handle, parent_window, options],
        )
        await self._call(msg)

    async def close_session(self, session_handle: str) -> None:
        msg = Message(
            destination=BUS_NAME,
            path=session_handle,
            interface="org.freedesktop.portal.Session",
            member="Close",
            signature="",
            body=[],
        )
        await self._call(msg)

    async def request_close(self, request_path: str) -> None:
        msg = Message(
            destination=BUS_NAME,
            path=request_path,
            interface=REQUEST_IFACE,
            member="Close",
            signature="",
            body=[],
        )
        await self._call(msg)

    def subscribe_activated(
        self, callback: Callable[[str, str, int, dict], None]
    ) -> None:
        self._subscribe_signal(
            SHORTCUT_IFACE,
            "Activated",
            callback,
        )

    def subscribe_deactivated(
        self, callback: Callable[[str, str, int, dict], None]
    ) -> None:
        self._subscribe_signal(
            SHORTCUT_IFACE,
            "Deactivated",
            callback,
        )

    def subscribe_shortcuts_changed(
        self, callback: Callable[[str, list], None]
    ) -> None:
        self._subscribe_signal(
            SHORTCUT_IFACE,
            "ShortcutsChanged",
            callback,
        )

    def _subscribe_signal(
        self, interface: str, member: str, callback: Callable
    ) -> None:
        key = (interface, member)

        def handler(msg: Message) -> None:
            if (
                msg.path == OBJECT_PATH
                and msg.interface == interface
                and msg.member == member
            ):
                callback(*msg.body)

        self._signal_handlers[key] = handler
        self._bus.add_message_handler(handler)

    async def _await_response(
        self, request_path: str
    ) -> dict:
        response_code = 0
        results: dict = {}
        event = asyncio.Event()

        def handler(msg: Message) -> None:
            nonlocal response_code, results
            if msg.path == request_path and msg.interface == REQUEST_IFACE and msg.member == "Response":
                response_code = msg.body[0]
                raw = msg.body[1]
                results = self._from_variant_dict(raw) if raw else {}
                event.set()

        self._bus.add_message_handler(handler)
        try:
            await asyncio.wait_for(event.wait(), timeout=30)
        except asyncio.TimeoutError:
            raise PortalCallError("Timed out waiting for portal response")
        finally:
            self._bus.remove_message_handler(handler)

        if not _response_ok(response_code):
            raise PortalResponseError(response_code)

        return results

    async def _call(self, msg: Message) -> Message:
        if not self._bus:
            raise PortalCallError("Not connected to D-Bus")
        try:
            reply = await self._bus.call(msg)
        except Exception as exc:
            raise PortalCallError(str(exc)) from exc
        if reply.message_type == MessageType.ERROR.value:
            raise PortalCallError(
                reply.body[0] if reply.body else "Unknown D-Bus error",
                dbus_error_name=reply.error_name,
            )
        return reply

    @staticmethod
    def _to_variant_dict(d: dict) -> dict:
        return {k: Variant("s", v) if isinstance(v, str) else Variant(type(v).__name__, v) for k, v in d.items()}

    @staticmethod
    def _from_variant_dict(d: dict) -> dict:
        return {k: v.value if isinstance(v, Variant) else v for k, v in d.items()}

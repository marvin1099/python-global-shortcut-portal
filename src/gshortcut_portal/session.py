from __future__ import annotations

import logging
from collections.abc import Callable

from gshortcut_portal.exceptions import SessionError
from gshortcut_portal.models import BoundShortcut, Shortcut, ShortcutEvent
from gshortcut_portal.portal import Portal
from gshortcut_portal.utils import generate_handle_token

logger = logging.getLogger(__name__)


class SessionCallback:
    def on_activated(self, event: ShortcutEvent) -> None:
        pass

    def on_deactivated(self, event: ShortcutEvent) -> None:
        pass

    def on_shortcuts_changed(self, session: GlobalShortcutsSession, shortcuts: list[BoundShortcut]) -> None:
        pass

    def on_error(self, error: Exception) -> None:
        pass


class GlobalShortcutsSession:
    def __init__(
        self,
        portal: Portal,
        app_id: str | None = None,
        callback: SessionCallback | None = None,
    ) -> None:
        self._portal = portal
        self._app_id = app_id
        self._callback = callback or SessionCallback()

        self._handle: str | None = None
        self._handle_token: str | None = None
        self._session_handle_token: str | None = None

        self._activated_handler: Callable | None = None
        self._deactivated_handler: Callable | None = None
        self._shortcuts_changed_handler: Callable | None = None

    @property
    def handle(self) -> str | None:
        return self._handle

    @property
    def connected(self) -> bool:
        return self._handle is not None

    async def connect(self) -> None:
        if not self._portal.connected:
            await self._portal.connect()

        if self._app_id:
            try:
                await self._portal.register(self._app_id)
            except Exception as exc:
                self._callback.on_error(exc)
                raise

        handle_token = generate_handle_token("session")
        session_token = generate_handle_token("s")
        self._handle_token = handle_token
        self._session_handle_token = session_token

        try:
            self._handle = await self._portal.create_session(handle_token, session_token)
        except Exception as exc:
            self._callback.on_error(exc)
            raise

        self._subscribe_signals()
        logger.info("Session created: %s", self._handle)

    async def close(self) -> None:
        if self._handle:
            try:
                await self._portal.close_session(self._handle)
            except Exception:
                pass
            self._handle = None
            self._unsubscribe_signals()

    async def bind(
        self,
        shortcuts: list[Shortcut],
        parent_window: str = "",
    ) -> list[BoundShortcut]:
        if not self._handle:
            raise SessionError("Session not created yet")

        dbus_list = [s.to_dbus_tuple() for s in shortcuts]
        try:
            result = await self._portal.bind_shortcuts(
                self._handle,
                dbus_list,
                parent_window,
            )
        except Exception as exc:
            self._callback.on_error(exc)
            raise

        bound = [BoundShortcut.from_dbus_pair(r) for r in result]
        return bound

    async def list_shortcuts(self) -> list[BoundShortcut]:
        if not self._handle:
            raise SessionError("Session not created yet")
        result = await self._portal.list_shortcuts(self._handle)
        return [BoundShortcut.from_dbus_pair(r) for r in result]

    async def configure(self, parent_window: str = "") -> None:
        if not self._handle:
            raise SessionError("Session not created yet")
        await self._portal.configure_shortcuts(self._handle, parent_window)

    def _subscribe_signals(self) -> None:
        self._activated_handler = self._portal.subscribe_activated(
            self._on_activated
        )
        self._deactivated_handler = self._portal.subscribe_deactivated(
            self._on_deactivated
        )
        self._shortcuts_changed_handler = (
            self._portal.subscribe_shortcuts_changed(
                self._on_shortcuts_changed
            )
        )

    def _unsubscribe_signals(self) -> None:
        self._activated_handler = None
        self._deactivated_handler = None
        self._shortcuts_changed_handler = None

    def _on_activated(
        self,
        session_handle: str,
        shortcut_id: str,
        timestamp: int,
        options: dict,
    ) -> None:
        if session_handle == self._handle:
            event = ShortcutEvent(
                session_handle=session_handle,
                shortcut_id=shortcut_id,
                timestamp=timestamp,
                options=options or {},
            )
            self._callback.on_activated(event)

    def _on_deactivated(
        self,
        session_handle: str,
        shortcut_id: str,
        timestamp: int,
        options: dict,
    ) -> None:
        if session_handle == self._handle:
            event = ShortcutEvent(
                session_handle=session_handle,
                shortcut_id=shortcut_id,
                timestamp=timestamp,
                options=options or {},
            )
            self._callback.on_deactivated(event)

    def _on_shortcuts_changed(
        self,
        session_handle: str,
        shortcuts: list,
    ) -> None:
        if session_handle == self._handle:
            bound = [BoundShortcut.from_dbus_pair(s) for s in shortcuts]
            self._callback.on_shortcuts_changed(self, bound)

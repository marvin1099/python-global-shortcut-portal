"""High-level session abstraction over the Global Shortcut portal.

Provides a convenient async API to create a portal session, bind/unbind
shortcuts, and react to activation/deactivation events through a callback.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from gshortcut_portal.exceptions import SessionError
from gshortcut_portal.models import BoundShortcut, Shortcut, ShortcutEvent
from gshortcut_portal.portal import Portal
from gshortcut_portal.utils import generate_handle_token

logger = logging.getLogger(__name__)


def _unwrap_options(opts: dict | None) -> dict:
    """Extract plain values from an options dict that may contain Variant wrappers."""
    if not opts:
        return {}
    return {k: getattr(v, "value", v) for k, v in opts.items()}


class SessionCallback:
    """Callback interface for session lifecycle and shortcut events."""

    def on_activated(self, event: ShortcutEvent) -> None:
        """Called when a shortcut is activated."""

    def on_deactivated(self, event: ShortcutEvent) -> None:
        """Called when a shortcut is deactivated."""

    def on_shortcuts_changed(
        self, session: GlobalShortcutsSession, shortcuts: list[BoundShortcut]
    ) -> None:
        """Called when the portal reports a change to the bound shortcuts list."""

    def on_error(self, error: Exception) -> None:
        """Called when an error occurs during a portal operation."""


class GlobalShortcutsSession:
    """A managed Global Shortcut portal session with signal subscription."""

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
        self._unsubscribers: list[Callable[[], None]] = []

    @property
    def handle(self) -> str | None:
        """The portal session handle, or None if not yet connected."""
        return self._handle

    @property
    def connected(self) -> bool:
        """True when the session has been successfully created."""
        return self._handle is not None

    async def connect(self) -> None:
        """Connect to D-Bus, optionally register the app, and create a portal session."""
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

        try:
            self._handle = await self._portal.create_session(
                handle_token, session_token
            )
        except Exception as exc:
            self._callback.on_error(exc)
            raise

        self._subscribe_signals()
        logger.info("Session created: %s", self._handle)

    async def close(self) -> None:
        """Close the portal session and unsubscribe all signal handlers."""
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
        """Bind a list of shortcuts; returns the BoundShortcut instances from the portal."""
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

    async def unbind_all(self) -> None:
        """Unbind all session-level shortcuts.

        On GNOME this clears the session. On Plasma/KDE, shortcuts are persisted per
        *app_id* — session-level unbinding has no visible effect. To fully clear
        persistent entries on Plasma, quit the app and remove them in
        System Settings > Keyboard > Shortcuts.
        """
        if not self._handle:
            raise SessionError("Session not created yet")
        await self._portal.bind_shortcuts(self._handle, [], "")

    async def list_shortcuts(self) -> list[BoundShortcut]:
        """Retrieve all currently bound shortcuts for this session."""
        if not self._handle:
            raise SessionError("Session not created yet")
        result = await self._portal.list_shortcuts(self._handle)
        return [BoundShortcut.from_dbus_pair(r) for r in result]

    async def configure(self, parent_window: str = "") -> None:
        """Open the desktop portal shortcut configuration UI."""
        if not self._handle:
            raise SessionError("Session not created yet")
        await self._portal.configure_shortcuts(self._handle, parent_window)

    def _subscribe_signals(self) -> None:
        """Subscribe to Activated, Deactivated, and ShortcutsChanged signals."""
        self._unsubscribers.append(self._portal.subscribe_activated(self._on_activated))
        self._unsubscribers.append(
            self._portal.subscribe_deactivated(self._on_deactivated)
        )
        self._unsubscribers.append(
            self._portal.subscribe_shortcuts_changed(self._on_shortcuts_changed)
        )

    def _unsubscribe_signals(self) -> None:
        """Remove all previously subscribed signal handlers."""
        for unsub in self._unsubscribers:
            unsub()
        self._unsubscribers.clear()

    def _on_activated(
        self,
        session_handle: str,
        shortcut_id: str,
        timestamp: int,
        options: dict,
    ) -> None:
        """Handle an Activated signal: wrap into ShortcutEvent and forward to callback."""
        if session_handle == self._handle:
            event = ShortcutEvent(
                session_handle=session_handle,
                shortcut_id=shortcut_id,
                timestamp=timestamp,
                options=_unwrap_options(options),
            )
            self._callback.on_activated(event)

    def _on_deactivated(
        self,
        session_handle: str,
        shortcut_id: str,
        timestamp: int,
        options: dict,
    ) -> None:
        """Handle a Deactivated signal: wrap into ShortcutEvent and forward to callback."""
        if session_handle == self._handle:
            event = ShortcutEvent(
                session_handle=session_handle,
                shortcut_id=shortcut_id,
                timestamp=timestamp,
                options=_unwrap_options(options),
            )
            self._callback.on_deactivated(event)

    def _on_shortcuts_changed(
        self,
        session_handle: str,
        shortcuts: list,
    ) -> None:
        """Handle ShortcutsChanged: parse bound shortcuts and forward to callback."""
        if session_handle == self._handle:
            bound = [
                BoundShortcut.from_dbus_pair((sid, _unwrap_options(opts)))
                for sid, opts in shortcuts
            ]
            self._callback.on_shortcuts_changed(self, bound)

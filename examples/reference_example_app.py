#!/usr/bin/env python3
"""
Reference example app for global-shortcut-portal.

Demonstrates the full lifecycle of a GlobalShortcuts session using the
xdg-desktop-portal GlobalShortcuts protocol on Wayland.

Run with:
    python examples/reference_example_app.py

Interactive controls (type in the terminal):
    r  — reset session (close + reopen)
    c  — open native config dialog (fallback to empty placeholders)
    b  — bind example shortcuts with default triggers
    e  — register example shortcuts without triggers
    q  — quit

Note on desktop environment persistence:
    Some DEs (notably Plasma/KDE) persist shortcut triggers per app_id.
    Once a shortcut ID is registered with a trigger, the DE remembers it
    across sessions. The portal cannot clear this persistent storage —
    use the native config dialog ([c]) to review or remove entries.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
import sys
import termios
import tty

from global_shortcut_portal import (
    BoundShortcut,
    GlobalShortcutsSession,
    Portal,
    SessionCallback,
    Shortcut,
    ShortcutEvent,
)

# ---------------------------------------------------------------------------
# Example shortcut definitions
# ---------------------------------------------------------------------------
# These use generic names and triggers to make it obvious they are examples.
# Replace these with your own application's shortcuts.

_EXAMPLE_SHORTCUTS = [
    Shortcut("example-action-1", "Example action 1", "<Control><Alt>space"),
    Shortcut("example-action-2", "Example action 2", "<Control><Shift>s"),
]

# Same IDs but without triggers — useful when the user should assign their own
# via the DE's native shortcut configuration dialog.
_EMPTY_SHORTCUTS = [
    Shortcut("example-action-1", "Example action 1"),
    Shortcut("example-action-2", "Example action 2"),
]


# ---------------------------------------------------------------------------
# Raw terminal helper
# ---------------------------------------------------------------------------
# Puts stdin in raw mode so we can read key presses character-by-character
# without waiting for Enter. Restores the terminal on exit.


@contextlib.contextmanager
def _raw_terminal():
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        mode = termios.tcgetattr(fd)
        mode[tty.OFLAG] |= termios.OPOST | termios.ONLCR
        termios.tcsetattr(fd, termios.TCSADRAIN, mode)
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


# ---------------------------------------------------------------------------
# Session callback handler
# ---------------------------------------------------------------------------


class AppCallback(SessionCallback):
    """Receives portal signals and prints them to the terminal.

    The _last_was_callback flag avoids blank lines between rapid-fire
    signal bursts while still separating callbacks from user-command output.
    """

    _last_was_callback = False

    def _sep(self) -> str:
        s = "" if AppCallback._last_was_callback else "\n"
        AppCallback._last_was_callback = True
        return s

    def on_activated(self, event: ShortcutEvent) -> None:
        print(
            f"{self._sep()}>>> Activated:   {event.shortcut_id}  (ts={event.timestamp})"
        )

    def on_deactivated(self, event: ShortcutEvent) -> None:
        print(
            f"{self._sep()}>>> Deactivated: {event.shortcut_id}  (ts={event.timestamp})"
        )

    def on_shortcuts_changed(
        self, session: GlobalShortcutsSession, shortcuts: list[BoundShortcut]
    ) -> None:
        print(f"{self._sep()}>>> Shortcuts changed:")
        for s in shortcuts:
            print(f"      {s.id}: {s.trigger_description}")

    def on_error(self, error: Exception) -> None:
        print(f"{self._sep()}>>> Error: {error}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _print_bindings(bound: list[BoundShortcut]) -> None:
    for s in bound:
        trigger = s.trigger_description or "(no trigger)"
        print(f"  - {s.id}: {trigger}")


def _print_help() -> None:
    print("  [r]eset  — close + reopen session")
    print("  [c]onfigure — native config dialog (fallback to empty placeholders)")
    print("  [b]ind  — register shortcuts with example triggers")
    print("  [e]mpty — register shortcuts without triggers")
    print("  [q]uit  — exit")


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------


async def main() -> None:
    portal = Portal()
    session: GlobalShortcutsSession | None = None
    stop = asyncio.Event()
    busy = False

    async def _create_session() -> GlobalShortcutsSession:
        """Create and connect a new GlobalShortcutsSession."""
        cb = AppCallback()
        s = GlobalShortcutsSession(
            portal,
            app_id="org.example.ReferenceExample",
            callback=cb,
        )
        await s.connect()
        print(f"Session handle: {s.handle}")
        return s

    async def _hint_if_stale() -> None:
        """List active shortcuts and warn if DE-persisted triggers linger."""
        try:
            current = await session.list_shortcuts()
        except Exception:
            return
        if current:
            print("Session shortcuts:")
            _print_bindings(current)
            for s in current:
                if s.trigger_description:
                    print(
                        "> Your desktop environment still shows old shortcuts from a previous session."
                    )
                    print(
                        "> Press [c] to open the native config dialog to review or clear them."
                    )
                    print(
                        "> You may need to close the app to make changes, then reopen it."
                    )
                    break
        else:
            print("Session has no shortcuts.")

    async def _on_r() -> None:
        """Reset: close the current session and create a fresh one."""
        nonlocal session, busy
        try:
            if session is not None:
                print("Closing old session...")
                await session.close()
            print("Creating new session...")
            session = await _create_session()
            print("Session reset — session-level bindings cleared.")
            await _hint_if_stale()
        except Exception as exc:
            print(f"Reset failed: {exc}", file=sys.stderr)
        finally:
            busy = False

    async def _on_c() -> None:
        """Open the DE's native config dialog; fall back to empty placeholders."""
        nonlocal busy
        try:
            if session is None or not session.connected:
                print("No active session", file=sys.stderr)
                return
            print("Requesting configure dialog...")
            await session.configure()
            current = await session.list_shortcuts()
            if current:
                print(f"Session has {len(current)} shortcut(s):")
                _print_bindings(current)
            else:
                print("No shortcuts registered — binding empty placeholders.")
                bound = await session.bind(_EMPTY_SHORTCUTS)
                _print_bindings(bound)
        except Exception as exc:
            print(f"Configure failed: {exc}", file=sys.stderr)
        finally:
            busy = False

    async def _on_b() -> None:
        """Bind example shortcuts with default triggers."""
        nonlocal busy
        try:
            if session is None or not session.connected:
                print("No active session", file=sys.stderr)
                return
            print("Binding example shortcuts...")
            bound = await session.bind(_EXAMPLE_SHORTCUTS)
            _print_bindings(bound)
            # Check whether the DE honoured our requested triggers.
            # Some DEs (Plasma) return their persisted values instead.
            expected = {
                "example-action-1": "<Control><Alt>space",
                "example-action-2": "<Control><Shift>s",
            }
            for s in bound:
                if s.trigger_description and s.trigger_description != expected.get(
                    s.id
                ):
                    print(
                        "> Your desktop environment still shows old shortcuts from a previous session."
                    )
                    print(
                        "> Press [c] to open the native config dialog to review or clear them."
                    )
                    print(
                        "> You may need to close the app to make changes, then reopen it."
                    )
                    break
        except Exception as exc:
            print(f"Bind failed: {exc}", file=sys.stderr)
            print(
                "> Your desktop environment still shows old shortcuts from a previous session.",
                file=sys.stderr,
            )
            print(
                "> Press [c] to open the native config dialog to review or clear them.",
                file=sys.stderr,
            )
            print(
                "> You may need to close the app to make changes, then reopen it.",
                file=sys.stderr,
            )
        finally:
            busy = False

    async def _on_e() -> None:
        """Register shortcuts without triggers (user assigns via DE config)."""
        nonlocal busy
        try:
            if session is None or not session.connected:
                print("No active session", file=sys.stderr)
                return
            print("Registering placeholder shortcuts (no trigger)...")
            await session.bind(_EMPTY_SHORTCUTS)
            await _hint_if_stale()
        except Exception as exc:
            print(f"Bind failed: {exc}", file=sys.stderr)
        finally:
            busy = False

    def _on_key() -> None:
        """Read a single keypress and dispatch to the matching handler."""
        nonlocal busy
        char = sys.stdin.read(1)
        if char in ("q", "\x03"):
            print("\n> Quit")
            stop.set()
        elif not busy:
            names = {"r": "Reset", "c": "Configure", "b": "Bind", "e": "Empty"}
            if char in names:
                AppCallback._last_was_callback = False
                print(f"\n> {names[char]}")
                busy = True
                tasks = {"r": _on_r, "c": _on_c, "b": _on_b, "e": _on_e}
                asyncio.ensure_future(tasks[char]())

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------

    loop = asyncio.get_running_loop()

    try:
        await portal.connect()
        version = await portal.get_portal_version()
        print(f"Connected. Portal GlobalShortcuts version: {version}")

        session = await _create_session()
        await _hint_if_stale()
        _print_help()

        loop.add_signal_handler(signal.SIGINT, stop.set)
        loop.add_signal_handler(signal.SIGTERM, stop.set)

        with _raw_terminal():
            loop.add_reader(sys.stdin.fileno(), _on_key)
            try:
                await stop.wait()
            finally:
                loop.remove_reader(sys.stdin.fileno())

    finally:
        print("Cleaning up...")
        if session is not None:
            try:
                await session.close()
            except Exception:
                pass
        await portal.close()
        print("Done.")


if __name__ == "__main__":
    asyncio.run(main())

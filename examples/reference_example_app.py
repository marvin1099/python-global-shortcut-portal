#!/usr/bin/env python3
"""
Reference example app for global-shortcut-portal.

Demonstrates the full lifecycle of a GlobalShortcuts session using the
xdg-desktop-portal GlobalShortcuts protocol on Wayland.

Run with:
    python examples/reference_example_app.py

Interactive controls (type in the terminal):
    r  — reset session (close + reopen); needed before binding a new set
    a  — grow the list: bind a third shortcut (resets the session first)
    f  — force empty: two reset+bind rounds that remove shortcuts
    b  — bind example shortcuts with default triggers
    e  — register example shortcuts without triggers
    l  — list currently bound shortcuts
    c  — open native config dialog
    q  — quit

Spec constraints (org.freedesktop.portal.GlobalShortcuts):
    BindShortcuts may only be attempted ONCE per session. To bind a
    different set of shortcuts, reset the session ([r]) and bind again.
    There is no portal method to remove or change an already-bound
    shortcut — use the native config dialog ([c]) instead.

Note on desktop environment persistence:
    Some DEs (notably Plasma/KDE) persist shortcut triggers per app_id.
    Resetting the session and binding a reduced set works per spec: the
    new bind set replaces the old one, so shortcuts missing from the new
    set are removed. But a shortcut that is still bound (same ID) keeps
    its stored trigger — to change one, remove it first (bind a set
    without it), then reset again and rebind the full set.
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
#
# Triggers use the XDG Shortcuts Specification format: modifiers joined by
# "+", followed by an xkbcommon key name (e.g. "CTRL+ALT+SPACE"). GTK-style
# accelerator strings like "<Control><Alt>space" are NOT valid here.

_EXAMPLE_SHORTCUTS = [
    Shortcut("example-action-1", "Example action 1", "CTRL+ALT+P"),
    Shortcut("example-action-2", "Example action 2", "CTRL+SHIFT+S"),
]

# A third shortcut bound by the [a] command to demonstrate how an app grows
# its shortcut list over time. The spec requires a fresh session for that.
_EXTRA_SHORTCUTS = [
    Shortcut("example-action-3", "Example action 3", "CTRL+SHIFT+SPACE"),
]

# The full set: example shortcuts plus the third one.
_FULL_SHORTCUTS = [*_EXAMPLE_SHORTCUTS, *_EXTRA_SHORTCUTS]

# The triggers we expect the DE to honour when binding each set.
_EXPECTED_TRIGGERS = {s.id: s.preferred_trigger or "" for s in _EXAMPLE_SHORTCUTS}
_EXTRA_EXPECTED_TRIGGERS = {s.id: s.preferred_trigger or "" for s in _EXTRA_SHORTCUTS}
_FULL_EXPECTED_TRIGGERS = {s.id: s.preferred_trigger or "" for s in _FULL_SHORTCUTS}

# Same IDs but without triggers — the user assigns their own via the DE's
# native shortcut configuration dialog. Derived from _EXAMPLE_SHORTCUTS so the
# two sets can never drift apart.
_EMPTY_SHORTCUTS = [Shortcut(s.id, s.description) for s in _EXAMPLE_SHORTCUTS]

# When binding _EMPTY_SHORTCUTS we expect no trigger to be assigned at all.
_EMPTY_EXPECTED = {s.id: "" for s in _EXAMPLE_SHORTCUTS}


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


def _normalize_trigger(s: str) -> str:
    """Normalize a trigger string for comparison.

    ``trigger_description`` is localized native text (e.g. "Ctrl+Alt+Space")
    while ``preferred_trigger`` uses the XDG spec format ("CTRL+ALT+SPACE").
    Comparing case-insensitively on alphanumerics ignores those differences.
    """
    return "".join(ch.lower() for ch in s if ch.isalnum())


def _print_unexpected_hint() -> None:
    """Print a hint when the bound shortcuts differ from what was requested."""
    print("> The bound shortcuts differ from what was requested.")
    print("> A trigger was probably changed by the user,")
    print("> or shortcut entries from a previous session still exist.")
    print("> Press [c] to change or delete shortcuts in the native config dialog.")
    print("> Note: deleting a shortcut may require closing this app first.")


def _check_bind_result(bound: list[BoundShortcut], expected: dict[str, str]) -> None:
    """Warn if any bound shortcut's trigger differs from *expected*.

    *expected* maps shortcut id to the XDG trigger string we asked for;
    an empty string means "no trigger assigned".
    """
    for s in bound:
        if _normalize_trigger(s.trigger_description) != _normalize_trigger(
            expected.get(s.id, "")
        ):
            _print_unexpected_hint()
            return


def _print_help() -> None:
    print("  [r]eset — close + reopen session (needed before re-binding)")
    print("  [a]dd  — grow the list: bind a third shortcut (resets session)")
    print("  [f]orce-empty — two reset+bind rounds that remove shortcuts")
    print("  [b]ind  — register shortcuts with example triggers")
    print("  [e]mpty — register shortcuts without triggers")
    print("  [l]ist  — list bound shortcuts")
    print("  [c]onfigure — open native config dialog (to change or delete shortcuts)")
    print("  [q]uit  — exit")


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------


async def main() -> None:
    portal = Portal()
    session: GlobalShortcutsSession | None = None
    bound = False  # BindShortcuts may only be attempted once per session
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
            if any(s.trigger_description for s in current):
                _print_unexpected_hint()
        else:
            print("Session has no shortcuts.")

    async def _reset_session() -> None:
        """Close the current session (if any) and create a fresh one."""
        nonlocal session, bound
        if session is not None:
            print("Closing old session...")
            await session.close()
        print("Creating new session...")
        session = await _create_session()
        bound = False

    async def _on_r() -> None:
        """Reset: close the current session and create a fresh one.

        A new session is the only spec-compliant way to bind a different
        (or larger) set of shortcuts, since BindShortcuts may only be
        attempted once per session.
        """
        nonlocal busy
        try:
            await _reset_session()
            print("Session reset — bind a fresh set of shortcuts.")
            await _hint_if_stale()
        except Exception as exc:
            print(f"Reset failed: {exc}", file=sys.stderr)
        finally:
            busy = False

    async def _on_a() -> None:
        """Grow the list: bind a third shortcut alongside the existing ones.

        BindShortcuts may only be attempted once per session, so adding
        shortcuts to an existing set requires a fresh session — reset if
        needed, then bind the full set.
        """
        nonlocal bound, busy
        try:
            if session is None or not session.connected:
                print("No active session", file=sys.stderr)
                return
            if bound:
                await _reset_session()
            print("Binding example shortcuts plus a third one...")
            bound_list = await session.bind(_FULL_SHORTCUTS)
            bound = True
            _print_bindings(bound_list)
            _check_bind_result(bound_list, _FULL_EXPECTED_TRIGGERS)
        except Exception as exc:
            print(f"Add failed: {exc}", file=sys.stderr)
            _print_unexpected_hint()
        finally:
            busy = False

    async def _on_f() -> None:
        """Force empty: demonstrate that a reduced bind set removes shortcuts.

        Two reset+bind rounds:
          1. bind only _EXTRA_SHORTCUTS  -> removes action-1 and action-2
          2. bind only _EMPTY_SHORTCUTS  -> removes action-3

        This works because each new session's BindShortcuts replaces the
        DE's per-app_id shortcut set (DE-dependent, see module docstring).
        """
        nonlocal bound, busy
        try:
            if session is None or not session.connected:
                print("No active session", file=sys.stderr)
                return
            print("Round 1: reset, then bind only the extra shortcut...")
            await _reset_session()
            bound_list = await session.bind(_EXTRA_SHORTCUTS)
            bound = True
            _print_bindings(bound_list)
            _check_bind_result(bound_list, _EXTRA_EXPECTED_TRIGGERS)
            print("> action-1 and action-2 should now be removed.")
            print("Round 2: reset, then bind only the empty placeholders...")
            await _reset_session()
            bound_list = await session.bind(_EMPTY_SHORTCUTS)
            bound = True
            _print_bindings(bound_list)
            _check_bind_result(bound_list, _EMPTY_EXPECTED)
            print("> action-3 should now be removed.")
        except Exception as exc:
            print(f"Force empty failed: {exc}", file=sys.stderr)
            _print_unexpected_hint()
        finally:
            busy = False

    async def _on_c() -> None:
        """Open the DE's native config dialog; fall back to empty placeholders."""
        nonlocal bound, busy
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
                if bound:
                    print(
                        "> Session already bound — press [r] to reset before re-binding.",
                        file=sys.stderr,
                    )
                else:
                    bound_list = await session.bind(_EMPTY_SHORTCUTS)
                    bound = True
                    _print_bindings(bound_list)
                    _check_bind_result(bound_list, _EMPTY_EXPECTED)
        except Exception as exc:
            print(f"Configure failed: {exc}", file=sys.stderr)
        finally:
            busy = False

    async def _on_b() -> None:
        """Bind example shortcuts with default triggers."""
        nonlocal bound, busy
        try:
            if session is None or not session.connected:
                print("No active session", file=sys.stderr)
                return
            if bound:
                print(
                    "> Session already bound — press [r] to reset before re-binding.",
                    file=sys.stderr,
                )
                return
            print("Binding example shortcuts...")
            bound_list = await session.bind(_EXAMPLE_SHORTCUTS)
            bound = True
            _print_bindings(bound_list)
            # Check whether the DE honoured our requested triggers.
            # Some DEs (Plasma) return their persisted values instead.
            _check_bind_result(bound_list, _EXPECTED_TRIGGERS)
        except Exception as exc:
            print(f"Bind failed: {exc}", file=sys.stderr)
            _print_unexpected_hint()
        finally:
            busy = False

    async def _on_e() -> None:
        """Register shortcuts without triggers (user assigns via DE config)."""
        nonlocal bound, busy
        try:
            if session is None or not session.connected:
                print("No active session", file=sys.stderr)
                return
            if bound:
                print(
                    "> Session already bound — press [r] to reset before re-binding.",
                    file=sys.stderr,
                )
                return
            print("Registering placeholder shortcuts (no trigger)...")
            bound_list = await session.bind(_EMPTY_SHORTCUTS)
            bound = True
            _print_bindings(bound_list)
            # Expect the DE to assign no trigger; warn if it kept any.
            _check_bind_result(bound_list, _EMPTY_EXPECTED)
        except Exception as exc:
            print(f"Bind failed: {exc}", file=sys.stderr)
            _print_unexpected_hint()
        finally:
            busy = False

    async def _on_l() -> None:
        """List the currently bound shortcuts for this session."""
        nonlocal busy
        try:
            if session is None or not session.connected:
                print("No active session", file=sys.stderr)
                return
            await _hint_if_stale()
        except Exception as exc:
            print(f"List failed: {exc}", file=sys.stderr)
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
            names = {
                "r": "Reset",
                "a": "Add",
                "f": "Force empty",
                "c": "Configure",
                "b": "Bind",
                "e": "Empty",
                "l": "List",
            }
            if char in names:
                AppCallback._last_was_callback = False
                print(f"\n> {names[char]}")
                busy = True
                tasks = {
                    "r": _on_r,
                    "a": _on_a,
                    "f": _on_f,
                    "c": _on_c,
                    "b": _on_b,
                    "e": _on_e,
                    "l": _on_l,
                }
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

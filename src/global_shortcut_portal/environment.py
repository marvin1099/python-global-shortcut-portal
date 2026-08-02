"""Runtime environment detection helpers.

These helpers are pure and side-effect free: they only read environment
variables and never touch D-Bus, so they are safe to call anywhere and
trivial to test. They let applications adapt to where they run — most
importantly whether they are sandboxed in Flatpak, where the portal
derives the app_id from the sandbox application ID instead of the D-Bus
sender.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Set by Flatpak inside the sandbox to the application ID (e.g.
# "page.codeberg.marvin1099.GlobalShortcutPortalExample").
_FLATPAK_ID_ENV = "FLATPAK_ID"

# Hint appended to connection errors raised while running inside Flatpak.
FLATPAK_HINT = (
    "\nRunning inside Flatpak: the sandbox provides a session bus and portal "
    "access by default. If you restricted D-Bus permissions, make sure portal "
    "APIs (org.freedesktop.portal.*) remain reachable."
)


def is_flatpak() -> bool:
    """Return True when the current process runs inside a Flatpak sandbox."""
    return _FLATPAK_ID_ENV in os.environ


def flatpak_id() -> str | None:
    """Return the Flatpak application ID, or None when not running in Flatpak."""
    return os.environ.get(_FLATPAK_ID_ENV)


def portal_app_id() -> str | None:
    """Return the app ID the portal attributes to this process.

    Inside Flatpak this is the sandbox application ID. On the host the portal
    derives the app ID from the D-Bus sender, which cannot be known in advance,
    so None is returned and the portal decides.
    """
    return flatpak_id()


def session_type() -> str | None:
    """Return the display session type ("wayland" or "x11"), else None."""
    if os.environ.get("WAYLAND_DISPLAY"):
        return "wayland"
    if os.environ.get("DISPLAY"):
        return "x11"
    return None


@dataclass(frozen=True)
class EnvironmentInfo:
    """Snapshot of the runtime environment relevant to the portal."""

    running_in_flatpak: bool
    flatpak_id: str | None
    portal_app_id: str | None
    session_type: str | None


def check_environment() -> EnvironmentInfo:
    """Collect the current runtime environment into an EnvironmentInfo."""
    return EnvironmentInfo(
        running_in_flatpak=is_flatpak(),
        flatpak_id=flatpak_id(),
        portal_app_id=portal_app_id(),
        session_type=session_type(),
    )

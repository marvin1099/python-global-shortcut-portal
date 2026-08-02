# Usage Guide

## Basic setup

```python
import asyncio
from global_shortcut_portal import (
    Portal,
    GlobalShortcutsSession,
    Shortcut,
    SessionCallback,
)


class MyCallback(SessionCallback):
    def on_activated(self, event):
        print(f"Activated: {event.shortcut_id}")


async def main():
    portal = Portal()
    await portal.connect()

    session = GlobalShortcutsSession(
        portal,
        app_id="org.example.MyApp",
        callback=MyCallback(),
    )
    await session.connect()
    ...
```

## Session lifecycle

### 1. Connect to the portal

```python
portal = Portal()
await portal.connect()
```

The `Portal` object wraps the D-Bus connection to
`org.freedesktop.portal.Desktop`. Connect once and reuse for all sessions.

### 2. Create a session

```python
session = GlobalShortcutsSession(
    portal,
    app_id="org.example.MyApp",  # reverse-DNS matching a .desktop file
    callback=MyCallback(),
)
await session.connect()
```

The session holds a set of registered shortcuts. On xdg-desktop-portal >= 1.20,
`connect()` also calls `Registry.Register(app_id)` to bind your D-Bus
connection to the app ID.

The `app_id` must match a `.desktop` file on the system (e.g.
`org.example.MyApp.desktop`).

### 3. Register shortcuts

```python
shortcuts = [
    Shortcut(
        id="toggle-sidebar",
        description="Toggle the sidebar",
        preferred_trigger="CTRL+ALT+SPACE",
    ),
    Shortcut(
        id="save-snapshot",
        description="Save a screenshot",
        preferred_trigger="CTRL+SHIFT+S",
    ),
]

bound = await session.bind(shortcuts)
for s in bound:
    print(f"{s.id}: {s.trigger_description}")
```

Each `Shortcut` has:
- `id` — unique identifier within your app (used in signal callbacks)
- `description` — human-readable name shown in DE settings
- `preferred_trigger` — optional, in [XDG shortcuts format](#trigger-format)

`bind()` returns a list of `BoundShortcut` objects reflecting what the
compositor actually assigned.

> **BindShortcuts is only allowed once per session.** The portal spec states:
> *"An application can only attempt bind shortcuts of a session once."*
> To bind a different or larger set of shortcuts, create a **new session**
> (`connect()` a fresh `GlobalShortcutsSession`, or close + recreate yours).

### 4. Handle signals

```python
class MyCallback(SessionCallback):
    def on_activated(self, event: ShortcutEvent) -> None:
        """Fired when the user presses the shortcut."""
        print(f"{event.shortcut_id} pressed at {event.timestamp}")

    def on_deactivated(self, event: ShortcutEvent) -> None:
        """Fired when the user releases the shortcut."""
        print(f"{event.shortcut_id} released")

    def on_shortcuts_changed(
        self, session: GlobalShortcutsSession, shortcuts: list[BoundShortcut]
    ) -> None:
        """Fired when the user or DE modifies shortcuts externally."""
        for s in shortcuts:
            print(f"  {s.id}: {s.trigger_description}")

    def on_error(self, error: Exception) -> None:
        """Fired when a D-Bus or session error occurs."""
        print(f"Error: {error}")
```

All callback methods have default no-op implementations — override only the
ones you need.

### 5. Open the native config dialog

```python
await session.configure()
```

Opens the DE's native shortcut configuration dialog for the current session.
This is where the user can review, change, or remove shortcut triggers.

On version 2 portals (Plasma 6+, GNOME 48+), this opens directly to the
relevant section of System Settings. On first-time setup for a new `app_id`,
a simplified initial-setup dialog may appear instead.

### 6. List registered shortcuts

```python
current = await session.list_shortcuts()
for s in current:
    print(f"  {s.id}: {s.trigger_description}")
```

### 7. Remove or change shortcuts

There is **no portal method** to unbind or update an already-bound shortcut.
Once bound, a shortcut can only be removed or re-triggered by the user via the
DE's native config dialog (`configure()`) or its keyboard settings.

If your app truly needs a different set of shortcuts at runtime, the
spec-compliant approach is to reset the session and bind the new set —
on Plasma this works as the spec describes. But a shortcut that is still
bound (same ID) keeps its trigger: it is never changed in place. To
change a shortcut's trigger you must first remove it (reset, then bind a
set without it), then reset again and rebind the full set with the new
trigger.

### 8. Close the session

```python
await session.close()
await portal.close()
```

Always close sessions and the portal when done. The portal has no built-in
timeout — unclosed sessions leak D-Bus signal subscriptions.

## Trigger format

Shortcut triggers follow the
[XDG Shortcuts Specification](https://specifications.freedesktop.org/shortcuts-spec/latest/):

```
MODIFIER[+MODIFIER]+key
```

Modifiers (uppercase): `CTRL`, `ALT`, `SHIFT`, `LOGO` (Super/Windows), `NUM`.
Note: this is **not** the GTK accelerator syntax (`<Control><Alt>space` is
invalid here and is silently ignored by some backends).

Key names are xkbcommon identifiers without the `XKB_KEY_` prefix:
`a`, `space`, `Return`, `F1`, `Page_Up`, etc.

Examples:
- `CTRL+ALT+SPACE`
- `CTRL+SHIFT+A`
- `LOGO+RETURN`

The utility module provides helpers:

```python
from global_shortcut_portal import parse_shortcut_trigger, format_shortcut_trigger

parsed = parse_shortcut_trigger("Ctrl+Shift+G")
# (frozenset({"CTRL", "SHIFT"}), "G")

formatted = format_shortcut_trigger(*parsed)
# "CTRL+SHIFT+G"
```

## Desktop environment persistence

Some DEs (notably Plasma/KDE) persist shortcut triggers per `app_id` in their
own configuration storage. Once a shortcut ID is registered with a trigger,
the DE remembers that trigger — even across session closes and rebinds.

This means:

- a reset session + rebind works as the spec describes: the new bind set
  replaces the previous one, so binding a set without a shortcut ID removes
  that shortcut
- `bind()` with a different trigger for an existing ID is **ignored** by
  Plasma: the stored trigger wins until the shortcut is removed
- changing a shortcut therefore needs two steps: reset and bind a set without
  it (removing it), then reset again and rebind the full set with the new
  trigger

## Example app

The reference implementation is at
[`examples/reference_example_app.py`](https://codeberg.org/marvin1099/python-global-shortcut-portal/src/branch/main/examples/reference_example_app.py) — a fully-commented
interactive application that demonstrates the complete lifecycle, including
session reset, config dialog, empty-placeholder registration, shortcut
listing, and DE persistence hints.

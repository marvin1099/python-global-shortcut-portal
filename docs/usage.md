# Usage Guide

## Basic setup

```python
import asyncio
from gshortcut_portal import Portal, GlobalShortcutsSession, Shortcut, SessionCallback

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
        preferred_trigger="<Control><Alt>space",
    ),
    Shortcut(
        id="save-snapshot",
        description="Save a screenshot",
        preferred_trigger="<Control><Shift>s",
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

### 7. Close the session

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
[modifier][+modifier]+key
```

Modifiers (case-insensitive): `CTRL`, `ALT`, `SHIFT`, `LOGO` (Super/Windows), `NUM`

Key names are xkbcommon identifiers without the `XKB_KEY_` prefix:
`a`, `space`, `Return`, `F1`, `Page_Up`, etc.

Examples:
- `<Control><Alt>space`
- `<Control><Shift>a`
- `<LOGO>Return`

The utility module provides helpers:

```python
from gshortcut_portal import parse_shortcut_trigger, format_shortcut_trigger

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

- `bind()` with a different trigger for an existing ID is **ignored** by Plasma
- `unbind_all()` (sends an empty shortcut list) does **not** clear persistent
  entries
- `close()` + `connect()` with the same `app_id` restores the old persisted
  triggers

**The only way to fully remove persistent entries** is to close the app and
delete them in the DE's shortcut settings (e.g. System Settings > Keyboard >
Shortcuts) while the app is not running.

## Example app

The repository includes
[`examples/reference_example_app.py`](../examples/reference_example_app.py) — a fully-commented
interactive application that demonstrates the complete lifecycle, including
session reset, config dialog, empty-placeholder registration, and DE
persistence hints.

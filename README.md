# gshortcut-portal

A pure-Python library for the Wayland **Global Shortcut Portal**
(`org.freedesktop.portal.GlobalShortcuts`). Lets any application register and
receive global keyboard shortcuts on Wayland — without X11 key grabbing.

## Requirements

- Python >= 3.10
- `dbus-next` (pure Python, no C extensions)
- A Wayland compositor with a Global Shortcuts portal backend
  (KDE Plasma 6+, GNOME 48+, Hyprland, etc.)

## Installation

```bash
pip install gshortcut-portal
```

## Quick Start

```python
import asyncio
from gshortcut_portal import GlobalShortcutsSession, Portal, Shortcut, SessionCallback

class MyCallback(SessionCallback):
    def on_activated(self, event):
        print(f"Shortcut activated: {event.shortcut_id}")

    def on_deactivated(self, event):
        print(f"Shortcut deactivated: {event.shortcut_id}")

async def main():
    portal = Portal()
    await portal.connect()

    session = GlobalShortcutsSession(
        portal,
        app_id="org.example.MyApp",
        callback=MyCallback(),
    )
    await session.connect()

    shortcuts = [
        Shortcut(
            id="toggle-overlay",
            description="Toggle overlay window",
            preferred_trigger="<Control><Alt>space",
        ),
    ]
    bound = await session.bind(shortcuts)
    for s in bound:
        print(f"Bound: {s.id} -> {s.trigger_description}")

    await asyncio.Event().wait()

asyncio.run(main())
```

## Sync Usage (with asyncio runner)

```python
import asyncio
from gshortcut_portal import GlobalShortcutsSession, Portal, Shortcut

async def run():
    portal = Portal()
    await portal.connect()
    session = GlobalShortcutsSession(portal, app_id="org.example.MyApp")
    await session.connect()
    bound = await session.bind([
        Shortcut("toggle", "Toggle sidebar"),
    ])
    for s in bound:
        print(f"  {s.id}: {s.trigger_description}")
    await session.close()
    await portal.close()

asyncio.run(run())
```

## Features

- Async API via `dbus-next` (pure Python asyncio D-Bus library)
- Session life-cycle management (create, bind, list, close)
- Supports `Registry.Register` for xdg-desktop-portal >= 1.20
- Full signal handling (Activated, Deactivated, ShortcutsChanged)
- Shortcut trigger parsing (XDG shortcuts specification)
- Version 2 portal features (ConfigureShortcuts)

## License

AGPL-3.0-only

# global-shortcut-portal

A pure-Python library for the Wayland **Global Shortcut Portal** (`org.freedesktop.portal.GlobalShortcuts`).  
Lets any application register and receive global keyboard shortcuts on Wayland, without X11 key grabbing.

AI was used heavily during development, with human review and testing of all code.  
This is a personal library I wanted and I'm sharing it in case it's useful to others.

## Requirements

- Python >= 3.10
- `dbus-next` (pure Python, no C extensions)
- A Wayland compositor with a Global Shortcuts portal backend
  (KDE Plasma 6+, GNOME 48+, Hyprland, etc.)

## Installation

```bash
pip install global-shortcut-portal
```

> On systems with an externally managed environment (e.g. recent Debian/Ubuntu,
> Fedora, Arch Linux with system Python) use `pip install --user` or a virtual
> environment. Alternatively, install with `uv`:
>
> ```bash
> uv pip install global-shortcut-portal
> ```
>
> For development, clone the repo and run:
> ```bash
> uv sync
> ```

## Reference Example

The repository includes a fully-commented reference app at
[`examples/reference_example_app.py`](examples/reference_example_app.py) that demonstrates the
complete session lifecycle with interactive controls:

| Key | Action |
|-----|--------|
| `b` | Bind example shortcuts with default triggers |
| `e` | Register shortcuts without triggers |
| `c` | Open the native config dialog |
| `r` | Reset the session |
| `q` | Quit |

```bash
python examples/reference_example_app.py
```

## Documentation

- [docs/overview.md](docs/overview.md) — the Global Shortcut Portal and this library
- [docs/usage.md](docs/usage.md) — full API guide with code examples
- [examples/reference_example_app.py](examples/reference_example_app.py) — interactive reference app

## Quick Start

```python
import asyncio
from global_shortcut_portal import GlobalShortcutsSession, Portal, Shortcut, SessionCallback

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

## Features

- Async API via `dbus-next` (pure Python asyncio D-Bus library)
- Session life-cycle management (create, bind, list, configure, close)
- Supports `Registry.Register` for xdg-desktop-portal >= 1.20
- Full signal handling (Activated, Deactivated, ShortcutsChanged)
- Shortcut trigger parsing and formatting (XDG shortcuts specification)
- Version 2 portal features (ConfigureShortcuts)

## Notes

- **Desktop environment persistence**: Some DEs (notably Plasma/KDE) persist
  shortcut triggers per `app_id`. Once registered, `BindShortcuts` cannot
  overwrite these stored values. Use the native config dialog or remove
  entries in System Settings > Keyboard > Shortcuts while the app is closed.

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
> uv sync --group dev
> ```

## Reference Example

The repository includes a fully-commented reference app at
[`examples/reference_example_app.py`](https://codeberg.org/marvin1099/python-global-shortcut-portal/src/branch/main/examples/reference_example_app.py) that demonstrates the
complete session lifecycle with interactive controls:

| Key | Action |
|-----|--------|
| `b` | Bind example shortcuts with default triggers |
| `a` | Grow the list: bind a third shortcut (resets session) |
| `f` | Force empty: two reset+bind rounds that remove shortcuts |
| `e` | Register shortcuts without triggers |
| `l` | List bound shortcuts |
| `c` | Open the native config dialog |
| `r` | Reset the session (needed before re-binding) |
| `q` | Quit |

```bash
python examples/reference_example_app.py
```

## Flatpak

xdg-desktop-portal was built for sandboxed apps, so this library runs unchanged
inside a Flatpak sandbox — portal access is granted by default, no D-Bus
permissions needed (see [docs/flatpak.md](docs/flatpak.md)). The only difference
is the app ID: the portal attributes shortcuts to the sandbox app ID
(`$FLATPAK_ID`). The library ships small detection helpers (`is_flatpak()`,
`flatpak_id()`, `portal_app_id()`, `session_type()`) for apps that need to know.

A ready-to-build Flatpak for the reference example lives in `flatpak/`:

```bash
flatpak-builder --force-clean --user --install flatpak/build \
  flatpak/page.codeberg.marvin1099.GlobalShortcutPortalExample.json
flatpak run page.codeberg.marvin1099.GlobalShortcutPortalExample
```

## Documentation

- [docs/overview.md](https://codeberg.org/marvin1099/python-global-shortcut-portal/src/branch/main/docs/overview.md) — the Global Shortcut Portal and this library
- [docs/usage.md](https://codeberg.org/marvin1099/python-global-shortcut-portal/src/branch/main/docs/usage.md) — full API guide with code examples
- [docs/flatpak.md](https://codeberg.org/marvin1099/python-global-shortcut-portal/src/branch/main/docs/flatpak.md) — running the library from a Flatpak sandbox
- [examples/reference_example_app.py](https://codeberg.org/marvin1099/python-global-shortcut-portal/src/branch/main/examples/reference_example_app.py) — interactive reference app

## Quick Start

```python
import asyncio
from global_shortcut_portal import (
    GlobalShortcutsSession,
    Portal,
    Shortcut,
    SessionCallback,
)


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
            preferred_trigger="CTRL+ALT+SPACE",
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

- **BindShortcuts is only allowed once per session.** There is no portal method
  to unbind or update a bound shortcut; use the native config dialog or create
  a new session to change the set.
- **Desktop environment persistence**: Some DEs (notably Plasma/KDE) persist
  shortcut triggers per `app_id`. A reset session + rebind works per spec: the
  new bind set replaces the old one, so a shortcut missing from the new set is
  removed. But a shortcut that is still bound (same ID) keeps its stored
  trigger — to change one, first bind a set without it, then reset again and
  rebind the full set with the new trigger.

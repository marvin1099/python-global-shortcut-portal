# Overview

`global-shortcut-portal` is a pure-Python async library for the
[`org.freedesktop.portal.GlobalShortcuts`](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.GlobalShortcuts.html)
D-Bus interface. It lets any application register global keyboard shortcuts on
Wayland without X11 key grabbing or platform-specific APIs.

## Why this library?

- **No C dependencies** — pure Python via `dbus-next`
- **Async-first** — built on asyncio, no GLib mainloop integration needed
- **Minimal** — a focused wrapper around the portal D-Bus interface, not a
  general-purpose portal library

## How it works

```
Your app (Python)
    ↕
This library (global-shortcut-portal)
    ↕ D-Bus
xdg-desktop-portal
    ↕
Compositor (KWin, Mutter, Hyprland, ...)
```

1. Your app connects to `xdg-desktop-portal` over the session D-Bus bus
2. It creates a *session* — a logical container for your shortcuts
3. It registers *shortcuts*: each has an ID, description, and optional preferred
   trigger in the [XDG shortcuts format](https://specifications.freedesktop.org/shortcuts-spec/latest/)
   (e.g. `CTRL+ALT+SPACE`)
4. The compositor (KWin, Mutter, Hyprland, etc.) decides the actual trigger;
   it honours your preference if the key combination is available and not
   conflicting with other shortcuts
5. When the user presses the trigger, the portal sends an `Activated` signal
6. When the user releases it, a `Deactivated` signal is sent
7. If the user reconfigures triggers via the DE's settings panel, a
   `ShortcutsChanged` signal notifies your app

Note: `BindShortcuts` may only be attempted **once per session**. To bind a
different set of shortcuts later, create a new session. There is no portal
method to unbind or update an already-bound shortcut — removal happens through
the DE's native config dialog.

## Requirements

- Python >= 3.10
- `dbus-next`
- A Wayland compositor with Global Shortcut portal support
  (KDE Plasma 6+, GNOME 48+, Hyprland, Sway, etc.)

## Reference

A fully-commented example app is at
[`examples/reference_example_app.py`](https://codeberg.org/marvin1099/python-global-shortcut-portal/src/branch/main/examples/reference_example_app.py). The
[usage guide](usage.md) covers the API in more detail.

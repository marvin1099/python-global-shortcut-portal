# Flatpak support

xdg-desktop-portal was designed for sandboxed (Flatpak) applications, and the
Global Shortcuts portal works from inside a Flatpak sandbox out of the box.
This library runs unchanged in Flatpak apps.

## Why it just works

- Flatpak's default D-Bus policy lets any app talk to portal APIs
  (`org.freedesktop.portal.*`) — no `--socket=session-bus` and no
  `--talk-name=org.freedesktop.portal.*` are required.
- `dbus-next` connects to the session bus through `DBUS_SESSION_BUS_ADDRESS`,
  which Flatpak sets to the sandbox's proxied bus.
- The library is pure Python (only dependency: `dbus-next`), so bundling it in
  a Flatpak is trivial.

The only thing that changes inside a sandbox is the app ID: the portal
attributes shortcuts to the sandbox application ID (`$FLATPAK_ID`) instead of
the host process name. On Plasma this ID is also what shortcuts persist under.

## Environment helpers

The library exposes small, dependency-free helpers (they only read environment
variables) so apps can adapt at runtime:

```python
from global_shortcut_portal import check_environment

info = check_environment()
print(info.running_in_flatpak)  # True inside a Flatpak sandbox
print(info.flatpak_id)  # e.g. page.codeberg.marvin1099.GlobalShortcutPortalExample
print(info.portal_app_id)  # the ID the portal will use (flatpak_id inside sandboxes)
print(info.session_type)  # "wayland" / "x11" / None
```

Individual functions are also exported: `is_flatpak()`, `flatpak_id()`,
`portal_app_id()`, `session_type()`.

`Portal.connect()` raises a `PortalCallError` with an actionable message when
no session bus is available (e.g. `DBUS_SESSION_BUS_ADDRESS` is unset), and
appends a Flatpak hint when it detects it is running inside a sandbox.

## Reference example as a Flatpak

`flatpak/` contains everything needed to build and run the reference example
app as a Flatpak:

- `page.codeberg.marvin1099.GlobalShortcutPortalExample.json` — the manifest
- `global-shortcut-example` — the wrapper entry point (installed to `/app/bin/`)

Permissions used (minimal):

| Finish arg | Why |
|---|---|
| `--socket=wayland` | Native Wayland socket (future window handles / config dialog) |
| `--socket=fallback-x11` | X11 fallback |
| `--share=ipc` | Shared memory for X11/Wayland client-server IPC |

No session-bus or portal `--talk-name` is needed: portal access is the sandbox
default.

### Build and run

Requires `flatpak` and `flatpak-builder`, plus the freedesktop runtime:

```bash
flatpak install -y flathub org.freedesktop.Platform//24.08 org.freedesktop.Sdk//24.08
flatpak-builder --force-clean --user --install flatpak/build \
  flatpak/page.codeberg.marvin1099.GlobalShortcutPortalExample.json
flatpak run page.codeberg.marvin1099.GlobalShortcutPortalExample
```

The manifest installs `dbus_next` and this library from the local checkout via
pip (network access is needed during the build to fetch `dbus_next`).

`flatpak/smoke-test.sh` automates this: it builds and installs the app, then
verifies the environment helpers and portal connectivity from inside the
sandbox.

### App ID

`page.codeberg.marvin1099.GlobalShortcutPortalExample` follows Flathub's
convention: projects hosted on codeberg.org use the `page.codeberg.` prefix. If
you fork or rename the project, pick an ID under a prefix you control and keep
it stable — Plasma persists shortcuts per app ID.

## Troubleshooting

- `flatpak run --log-session-bus <app-id>` prints the D-Bus traffic and can
  show whether portal calls are being filtered.
- If your app also needs other D-Bus services, add their `--talk-name` to
  `finish-args`; do not grant `--socket=session-bus` unless you must.
- Plasma keeps shortcuts per app ID: a shortcut bound by the Flatpak example
  persists under the full sandbox ID. To change one, remove it first (bind a
  set without it), then reset and rebind the full set with the new trigger.
- On filesystems where `chmod` is a no-op (e.g. an NTFS `fuseblk` mount), Flatpak
  install rejects the built files as world-writable. Build with the build dir,
  state dir, and repo on a chmod-supporting filesystem such as tmpfs:

  ```bash
  flatpak-builder --force-clean --user --install \
    --repo=/tmp/gsfp-repo --state-dir=/tmp/gsfp-state \
    /tmp/gsfp-build flatpak/page.codeberg.marvin1099.GlobalShortcutPortalExample.json
  ```

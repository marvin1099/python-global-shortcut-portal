#!/bin/sh
# Smoke test for the Flatpak packaging of the reference example.
#
# Builds and installs the app, then verifies the library actually works
# inside the sandbox:
#   1. the sandbox environment helpers report the Flatpak app ID
#   2. the app connects to the portal through the proxied session bus
#
# The single-file .flatpak distribution step (flatpak build-bundle) is not
# needed to exercise shortcuts, so it is intentionally skipped.
#
# Usage: flatpak/smoke-test.sh

set -eu

HERE="$(cd "$(dirname "$0")" && pwd)"
MANIFEST="$HERE/page.codeberg.marvin1099.GlobalShortcutPortalExample.json"
APP_ID="page.codeberg.marvin1099.GlobalShortcutPortalExample"

for cmd in flatpak flatpak-builder; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "error: $cmd not found" >&2
        exit 1
    fi
done

# Build dir, state dir, and repo must live on a chmod-supporting filesystem
# (Flatpak install rejects built files as world-writable on NTFS/fuseblk).
WORKDIR="${TMPDIR:-/tmp}/gsfp-smoke-$$"
BUILD_DIR="$WORKDIR/build"
STATE_DIR="$WORKDIR/state"
REPO_DIR="$WORKDIR/repo"
mkdir -p "$BUILD_DIR" "$STATE_DIR" "$REPO_DIR"
trap 'rm -rf "$WORKDIR"' EXIT

echo "==> Building and installing $APP_ID"
flatpak-builder --force-clean --user --install \
    --repo="$REPO_DIR" --state-dir="$STATE_DIR" \
    "$BUILD_DIR" "$MANIFEST"

echo "==> Checking imports and environment helpers inside the sandbox"
flatpak run --command=python3 "$APP_ID" - <<'PY'
from global_shortcut_portal import check_environment

info = check_environment()
print(info)
assert info.running_in_flatpak, "expected running_in_flatpak=True in the sandbox"
assert info.flatpak_id == "page.codeberg.marvin1099.GlobalShortcutPortalExample", (
    f"unexpected flatpak id: {info.flatpak_id}"
)
assert info.portal_app_id == info.flatpak_id, "portal app id must match flatpak id"
assert info.session_type in ("wayland", "x11"), "expected a display session"
print("OK: environment helpers report the Flatpak sandbox")
PY

echo "==> Connecting to the portal through the sandbox"
if timeout 30 flatpak run "$APP_ID" </dev/null \
    | grep -q "Connected. Portal GlobalShortcuts version:"; then
    echo "OK: portal reachable from inside the sandbox"
else
    echo "error: the app did not connect to the portal" >&2
    exit 1
fi

echo "Smoke test passed."

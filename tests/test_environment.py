from global_shortcut_portal.environment import (
    EnvironmentInfo,
    check_environment,
    flatpak_id,
    is_flatpak,
    portal_app_id,
    session_type,
)

APP_ID = "page.codeberg.marvin1099.GlobalShortcutPortalExample"


def test_is_flatpak_false_by_default(monkeypatch):
    monkeypatch.delenv("FLATPAK_ID", raising=False)
    assert is_flatpak() is False
    assert flatpak_id() is None
    assert portal_app_id() is None


def test_is_flatpak_true(monkeypatch):
    monkeypatch.setenv("FLATPAK_ID", APP_ID)
    assert is_flatpak() is True
    assert flatpak_id() == APP_ID
    assert portal_app_id() == APP_ID


def test_session_type_wayland(monkeypatch):
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.delenv("DISPLAY", raising=False)
    assert session_type() == "wayland"


def test_session_type_x11(monkeypatch):
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("DISPLAY", ":0")
    assert session_type() == "x11"


def test_session_type_unknown(monkeypatch):
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("DISPLAY", raising=False)
    assert session_type() is None


def test_check_environment(monkeypatch):
    monkeypatch.setenv("FLATPAK_ID", APP_ID)
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.delenv("DISPLAY", raising=False)
    info = check_environment()
    assert info == EnvironmentInfo(
        running_in_flatpak=True,
        flatpak_id=APP_ID,
        portal_app_id=APP_ID,
        session_type="wayland",
    )

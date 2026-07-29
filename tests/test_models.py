from gshortcut_portal.exceptions import PortalResponseError
from gshortcut_portal.models import BoundShortcut, Shortcut
from gshortcut_portal.utils import format_shortcut_trigger, parse_shortcut_trigger


class TestShortcutModel:
    def test_to_dbus_tuple_minimal(self):
        s = Shortcut(id="test", description="Test shortcut")
        result = s.to_dbus_tuple()
        assert result == ("test", {"description": "Test shortcut"})

    def test_to_dbus_tuple_with_trigger(self):
        s = Shortcut(id="test", description="Test", preferred_trigger="CTRL+ALT+a")
        result = s.to_dbus_tuple()
        assert result == (
            "test",
            {
                "description": "Test",
                "preferred_trigger": "CTRL+ALT+a",
            },
        )

    def test_bound_shortcut_from_dbus_pair(self):
        pair = (
            "my-id",
            {
                "description": "My Shortcut",
                "trigger_description": "Press Control+Alt+A",
            },
        )
        bs = BoundShortcut.from_dbus_pair(pair)
        assert bs.id == "my-id"
        assert bs.description == "My Shortcut"
        assert bs.trigger_description == "Press Control+Alt+A"


class TestShortcutTriggerParsing:
    def test_simple_key(self):
        mods, key = parse_shortcut_trigger("a")
        assert mods == frozenset()
        assert key == "a"

    def test_with_modifiers(self):
        mods, key = parse_shortcut_trigger("CTRL+ALT+a")
        assert "CTRL" in mods
        assert "ALT" in mods
        assert key == "a"

    def test_logo_modifier(self):
        mods, key = parse_shortcut_trigger("LOGO+Return")
        assert "LOGO" in mods
        assert key == "Return"

    def test_format(self):
        result = format_shortcut_trigger({"CTRL", "ALT"}, "a")
        assert result == "ALT+CTRL+a"

    def test_format_no_mods(self):
        result = format_shortcut_trigger(set(), "Return")
        assert result == "Return"


class TestExceptions:
    def test_portal_response_error(self):
        err = PortalResponseError(1, "User cancelled")
        assert err.response_code == 1
        assert "User cancelled" in str(err)

    def test_portal_response_error_default(self):
        err = PortalResponseError(0)
        assert err.response_code == 0

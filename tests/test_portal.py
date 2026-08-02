import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from dbus_next import Variant

from global_shortcut_portal.exceptions import (
    PortalCallError,
    PortalResponseError,
    SessionError,
)
from global_shortcut_portal.models import BoundShortcut, Shortcut, ShortcutEvent
from global_shortcut_portal.portal import Portal
from global_shortcut_portal.session import (
    GlobalShortcutsSession,
    SessionCallback,
    _unwrap_options,
)


def _fake_msg(body, path="", interface="", member="", msg_type=1):
    msg = MagicMock()
    msg.body = body
    msg.path = path
    msg.interface = interface
    msg.member = member
    msg.message_type = msg_type
    if msg_type == 3:
        msg.error_name = "org.freedesktop.DBus.Error.Failed"
    return msg


@pytest.fixture
def mock_bus():
    bus = MagicMock()
    bus.unique_name = ":1.123"
    bus.call = AsyncMock()
    bus.add_message_handler = MagicMock()
    bus.remove_message_handler = MagicMock()
    bus.disconnect = MagicMock()
    bus.connect = AsyncMock(return_value=bus)
    return bus


@pytest.fixture
def portal(mock_bus, monkeypatch):
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", "unix:path=/tmp/fake-bus")
    patcher = patch("global_shortcut_portal.portal.MessageBus", return_value=mock_bus)
    patcher.start()
    p = Portal()
    yield p
    patcher.stop()


@pytest.fixture
def connected_portal(portal, mock_bus):
    """Portal that is connected and has _await_response pre-mocked."""
    portal.connect = AsyncMock()
    portal._bus = mock_bus
    portal._connected = True
    portal._unique_name = ":1.123"
    portal._await_response = AsyncMock()
    yield portal


class TestPortalConnection:
    @pytest.mark.asyncio
    async def test_connect(self, portal, mock_bus):
        await portal.connect()
        assert portal.connected is True
        assert portal._bus is mock_bus

    @pytest.mark.asyncio
    async def test_connect_idempotent(self, portal, mock_bus):
        await portal.connect()
        await portal.connect()
        mock_bus.connect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close(self, portal, mock_bus):
        await portal.connect()
        await portal.close()
        assert portal.connected is False
        assert portal._bus is None
        mock_bus.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_missing_session_bus(self, monkeypatch):
        monkeypatch.delenv("DBUS_SESSION_BUS_ADDRESS", raising=False)
        p = Portal()
        with pytest.raises(PortalCallError, match="DBUS_SESSION_BUS_ADDRESS"):
            await p.connect()

    @pytest.mark.asyncio
    async def test_connect_missing_session_bus_flatpak_hint(self, monkeypatch):
        monkeypatch.delenv("DBUS_SESSION_BUS_ADDRESS", raising=False)
        monkeypatch.setenv("FLATPAK_ID", "org.example.App")
        p = Portal()
        with pytest.raises(PortalCallError, match="Running inside Flatpak"):
            await p.connect()

    @pytest.mark.asyncio
    async def test_connect_dbus_failure(self, monkeypatch, mock_bus):
        monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", "unix:path=/tmp/fake-bus")
        mock_bus.connect.side_effect = Exception("boom")
        with patch("global_shortcut_portal.portal.MessageBus", return_value=mock_bus):
            p = Portal()
            with pytest.raises(PortalCallError, match="boom"):
                await p.connect()


class TestPortalCalls:
    @pytest.mark.asyncio
    async def test_get_portal_version(self, portal, mock_bus):
        msg = _fake_msg([MagicMock(value=2)])
        mock_bus.call.return_value = msg
        await portal.connect()
        version = await portal.get_portal_version()
        assert version == 2

    @pytest.mark.asyncio
    async def test_get_portal_version_dbus_error(self, portal, mock_bus):
        mock_bus.call.side_effect = Exception("Connection refused")
        await portal.connect()
        with pytest.raises(PortalCallError, match="Connection refused"):
            await portal.get_portal_version()

    @pytest.mark.asyncio
    async def test_register(self, portal, mock_bus):
        mock_bus.call.return_value = _fake_msg([])
        await portal.connect()
        await portal.register("org.example.App")
        call = mock_bus.call.call_args[0][0]
        assert call.member == "Register"

    @pytest.mark.asyncio
    async def test_call_dbus_error(self, portal, mock_bus):
        err = _fake_msg(["Access denied"], msg_type=3)
        mock_bus.call.return_value = err
        await portal.connect()
        with pytest.raises(PortalCallError, match="Access denied"):
            await portal.get_portal_version()

    @pytest.mark.asyncio
    async def test_create_session(self, connected_portal):
        connected_portal._await_response.return_value = {
            "session_handle": "/org/freedesktop/portal/session/test"
        }
        handle = await connected_portal.create_session("htok", "stok")
        assert handle == "/org/freedesktop/portal/session/test"

    @pytest.mark.asyncio
    async def test_bind_shortcuts(self, connected_portal):
        connected_portal._await_response.return_value = {
            "shortcuts": [
                (
                    "toggle",
                    {
                        "description": "Toggle it",
                        "trigger_description": "Ctrl+T",
                    },
                ),
            ]
        }
        shortcuts = [("toggle", {"description": "Toggle it"})]
        result = await connected_portal.bind_shortcuts("/session/test", shortcuts)
        assert len(result) == 1
        assert result[0][0] == "toggle"

    @pytest.mark.asyncio
    async def test_list_shortcuts(self, connected_portal):
        connected_portal._await_response.return_value = {
            "shortcuts": [
                ("toggle", {"description": "Toggle", "trigger_description": "Ctrl+T"}),
            ]
        }
        result = await connected_portal.list_shortcuts("/session/test")
        assert len(result) == 1
        assert result[0][1]["trigger_description"] == "Ctrl+T"

    @pytest.mark.asyncio
    async def test_list_shortcuts_empty(self, connected_portal):
        connected_portal._await_response.return_value = {}
        result = await connected_portal.list_shortcuts("/session/test")
        assert result == []

    @pytest.mark.asyncio
    async def test_response_error(self, connected_portal):
        connected_portal._await_response.side_effect = PortalResponseError(1)
        with pytest.raises(PortalResponseError):
            await connected_portal.create_session("htok", "stok")


class TestSessionLifecycle:
    @pytest.mark.asyncio
    async def test_connect_and_bind(self, connected_portal):
        # Simulate create_session returning a handle
        connected_portal.create_session = AsyncMock(
            return_value="/org/freedesktop/portal/session/test1"
        )
        # Simulate bind_shortcuts returning bound shortcuts
        connected_portal.bind_shortcuts = AsyncMock(
            return_value=[
                (
                    "toggle",
                    {
                        "description": "Toggle sidebar",
                        "trigger_description": "Press Ctrl+Alt+T",
                    },
                ),
            ]
        )

        session = GlobalShortcutsSession(connected_portal)
        await session.connect()
        assert session.handle == "/org/freedesktop/portal/session/test1"
        assert session.connected is True

        bound = await session.bind(
            [
                Shortcut("toggle", "Toggle sidebar"),
            ]
        )
        assert len(bound) == 1
        assert bound[0].id == "toggle"
        assert bound[0].trigger_description == "Press Ctrl+Alt+T"

    @pytest.mark.asyncio
    async def test_list_and_configure(self, connected_portal):
        connected_portal.create_session = AsyncMock(return_value="/session/t2")
        connected_portal.list_shortcuts = AsyncMock(
            return_value=[
                ("first", {"description": "First", "trigger_description": "Ctrl+F"}),
            ]
        )
        connected_portal.configure_shortcuts = AsyncMock()

        session = GlobalShortcutsSession(connected_portal)
        await session.connect()

        listed = await session.list_shortcuts()
        assert len(listed) == 1
        assert listed[0].trigger_description == "Ctrl+F"

        await session.configure("")
        connected_portal.configure_shortcuts.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_register_app_id(self, connected_portal):
        connected_portal.create_session = AsyncMock(return_value="/session/t3")
        connected_portal.register = AsyncMock()

        session = GlobalShortcutsSession(connected_portal, app_id="org.example.App")
        await session.connect()

        connected_portal.register.assert_awaited_once_with("org.example.App")

    @pytest.mark.asyncio
    async def test_close_session(self, connected_portal):
        connected_portal.create_session = AsyncMock(return_value="/session/t4")
        connected_portal.close_session = AsyncMock()

        session = GlobalShortcutsSession(connected_portal)
        await session.connect()
        assert session.connected is True

        await session.close()
        assert session.connected is False
        connected_portal.close_session.assert_awaited_once_with("/session/t4")

    @pytest.mark.asyncio
    async def test_bind_without_connect_raises(self, connected_portal):
        session = GlobalShortcutsSession(connected_portal)
        with pytest.raises(SessionError, match="Session not created"):
            await session.bind([Shortcut("test", "Test")])


class TestCallback:
    def test_default_callback_does_not_raise(self):
        cb = SessionCallback()
        event = ShortcutEvent("s1", "toggle", 12345)
        cb.on_activated(event)
        cb.on_deactivated(event)
        cb.on_shortcuts_changed(None, [])
        cb.on_error(Exception("test"))


class TestBoundShortcutConversion:
    def test_from_dbus_pair_full(self):
        pair = (
            "my-id",
            {
                "description": "My Shortcut",
                "trigger_description": "Ctrl+Alt+X",
            },
        )
        bs = BoundShortcut.from_dbus_pair(pair)
        assert bs.id == "my-id"
        assert bs.description == "My Shortcut"
        assert bs.trigger_description == "Ctrl+Alt+X"

    def test_from_dbus_pair_minimal(self):
        pair = ("my-id", {})
        bs = BoundShortcut.from_dbus_pair(pair)
        assert bs.id == "my-id"
        assert bs.description == ""
        assert bs.trigger_description == ""


class TestShortcutModel:
    def test_to_dbus_tuple_minimal(self):
        s = Shortcut(id="test", description="Test shortcut")
        assert s.to_dbus_tuple() == ("test", {"description": "Test shortcut"})

    def test_to_dbus_tuple_with_trigger(self):
        s = Shortcut(id="test", description="Test", preferred_trigger="CTRL+ALT+a")
        assert s.to_dbus_tuple() == (
            "test",
            {
                "description": "Test",
                "preferred_trigger": "CTRL+ALT+a",
            },
        )


class TestUnwrapOptions:
    def test_none(self):
        assert _unwrap_options(None) == {}

    def test_empty(self):
        assert _unwrap_options({}) == {}

    def test_plain_dict(self):
        assert _unwrap_options({"a": "1", "b": "2"}) == {"a": "1", "b": "2"}

    def test_with_variants(self):
        result = _unwrap_options(
            {
                "activation_token": Variant("s", "tok123"),
            }
        )
        assert result == {"activation_token": "tok123"}


class TestSignalHandlers:
    @pytest.mark.asyncio
    async def test_activated_dispatched(self, connected_portal):
        connected_portal.create_session = AsyncMock(return_value="/session/sig1")
        events = []

        class Callback(SessionCallback):
            def on_activated(self, event):
                events.append(event)

        session = GlobalShortcutsSession(connected_portal, callback=Callback())
        await session.connect()

        session._on_activated(
            "/session/sig1",
            "my-shortcut",
            123456,
            {"activation_token": "tok"},
        )
        assert len(events) == 1
        assert events[0].shortcut_id == "my-shortcut"
        assert events[0].timestamp == 123456

    @pytest.mark.asyncio
    async def test_activated_unwraps_variants(self, connected_portal):
        connected_portal.create_session = AsyncMock(return_value="/session/sig2")
        events = []

        class Callback(SessionCallback):
            def on_activated(self, event):
                events.append(event)

        session = GlobalShortcutsSession(connected_portal, callback=Callback())
        await session.connect()

        session._on_activated(
            "/session/sig2",
            "my-shortcut",
            123456,
            {"activation_token": Variant("s", "tok123")},
        )
        assert events[0].options == {"activation_token": "tok123"}

    @pytest.mark.asyncio
    async def test_deactivated_unwraps_variants(self, connected_portal):
        connected_portal.create_session = AsyncMock(return_value="/session/sig3")
        events = []

        class Callback(SessionCallback):
            def on_deactivated(self, event):
                events.append(event)

        session = GlobalShortcutsSession(connected_portal, callback=Callback())
        await session.connect()

        session._on_deactivated(
            "/session/sig3",
            "my-shortcut",
            123456,
            {"activation_token": Variant("s", "tok456")},
        )
        assert events[0].options == {"activation_token": "tok456"}

    @pytest.mark.asyncio
    async def test_shortcuts_changed_unwraps_variants(self, connected_portal):
        connected_portal.create_session = AsyncMock(return_value="/session/sig4")
        shortcuts_list = []

        class Callback(SessionCallback):
            def on_shortcuts_changed(self, session, shortcuts):
                shortcuts_list.extend(shortcuts)

        session = GlobalShortcutsSession(connected_portal, callback=Callback())
        await session.connect()

        session._on_shortcuts_changed(
            "/session/sig4",
            [
                [
                    "toggle",
                    {
                        "description": Variant("s", "Toggle it"),
                        "trigger_description": Variant("s", "Ctrl+T"),
                    },
                ],
            ],
        )
        assert len(shortcuts_list) == 1
        assert shortcuts_list[0].id == "toggle"
        assert shortcuts_list[0].trigger_description == "Ctrl+T"


class TestMessageBody:
    @pytest.mark.asyncio
    async def test_bind_shortcuts_uses_lists_for_structs(self, portal, mock_bus):
        mock_bus.call.return_value = _fake_msg(["/request/path"])
        portal._bus = mock_bus
        portal._connected = True
        portal._unique_name = ":1.123"
        portal._await_response = AsyncMock(return_value={"shortcuts": []})

        await portal.bind_shortcuts(
            "/session/test",
            [("toggle", {"description": "Test"})],
        )

        msg = mock_bus.call.call_args[0][0]
        dbus_shortcuts = msg.body[1]
        assert len(dbus_shortcuts) == 1
        assert isinstance(dbus_shortcuts[0], list), (
            "each D-Bus struct must be a list, not tuple"
        )
        assert dbus_shortcuts[0][0] == "toggle"


class TestAwaitResponseCloseRace:
    @pytest.mark.asyncio
    async def test_bus_closed_while_pending_does_not_crash(self, portal, mock_bus):
        portal._bus = mock_bus
        portal._connected = True
        portal._unique_name = ":1.123"
        captured = {}

        def record_handler(handler):
            captured["handler"] = handler

        mock_bus.add_message_handler.side_effect = record_handler

        async def wait_with_close():
            task = asyncio.create_task(portal._await_response("/request/x"))
            await asyncio.sleep(0)
            handler = captured["handler"]
            handler(
                _fake_msg(
                    [0, {}],
                    path="/request/x",
                    interface="org.freedesktop.portal.Request",
                    member="Response",
                )
            )
            portal._bus = None
            await asyncio.sleep(0)
            return await task

        results = await wait_with_close()
        assert results == {}
        mock_bus.remove_message_handler.assert_not_called()


class TestCloseSessionSubscriptions:
    @pytest.mark.asyncio
    async def test_close_clears_subscribers(self, connected_portal):
        connected_portal.create_session = AsyncMock(return_value="/session/cu1")
        connected_portal.close_session = AsyncMock()

        session = GlobalShortcutsSession(connected_portal)
        await session.connect()

        assert len(session._unsubscribers) == 3

        await session.close()
        assert len(session._unsubscribers) == 0

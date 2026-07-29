from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class Shortcut:
    id: str
    description: str
    preferred_trigger: str | None = None

    def to_dbus_tuple(self) -> tuple[str, dict[str, str]]:
        options: dict[str, str] = {"description": self.description}
        if self.preferred_trigger:
            options["preferred_trigger"] = self.preferred_trigger
        return (self.id, options)


@dataclass
class BoundShortcut:
    id: str
    description: str
    trigger_description: str

    @classmethod
    def from_dbus_pair(cls, pair: tuple[str, dict]) -> BoundShortcut:
        shortcut_id, options = pair
        return cls(
            id=shortcut_id,
            description=options.get("description", ""),
            trigger_description=options.get("trigger_description", ""),
        )


@dataclass
class ShortcutEvent:
    session_handle: str
    shortcut_id: str
    timestamp: int
    options: dict = field(default_factory=dict)


@dataclass
class SessionInfo:
    handle: str
    portal_version: int

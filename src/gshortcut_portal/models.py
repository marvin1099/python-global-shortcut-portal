"""Data models for the Global Shortcut portal.

Defines the dataclasses used to represent shortcuts before binding,
the portal response for a bound shortcut, and activation/deactivation events.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Shortcut:
    """A shortcut to be registered with the portal."""

    id: str
    description: str
    preferred_trigger: str | None = None

    def to_dbus_tuple(self) -> tuple[str, dict[str, str]]:
        """Serialize to a (shortcut_id, options) pair for D-Bus."""
        options: dict[str, str] = {"description": self.description}
        if self.preferred_trigger:
            options["preferred_trigger"] = self.preferred_trigger
        return (self.id, options)


@dataclass
class BoundShortcut:
    """A shortcut returned by the portal after binding, including its trigger description."""

    id: str
    description: str
    trigger_description: str

    @classmethod
    def from_dbus_pair(cls, pair: tuple[str, dict]) -> BoundShortcut:
        """Construct a BoundShortcut from a D-Bus (shortcut_id, options) pair."""
        shortcut_id, options = pair
        return cls(
            id=shortcut_id,
            description=options.get("description", ""),
            trigger_description=options.get("trigger_description", ""),
        )


@dataclass
class ShortcutEvent:
    """Event payload for shortcut activation/deactivation signals."""

    session_handle: str
    shortcut_id: str
    timestamp: int
    options: dict = field(default_factory=dict)

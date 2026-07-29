"""Utility functions for the Global Shortcut portal library.

Includes helpers for parsing/formatting shortcut trigger strings and
generating unique handle tokens for portal sessions.
"""

from __future__ import annotations

import secrets
import string

# Characters allowed in a shortcut key name
_LEGAL_KEY_CHARS = frozenset(string.ascii_letters + string.digits + "_")

# Recognised modifier key names (case-insensitive)
_MODIFIER_NAMES = frozenset(
    {"CTRL", "ALT", "SHIFT", "LOGO", "NUM", "SUPER", "HYPER", "META"}
)


def parse_shortcut_trigger(trigger: str) -> tuple[frozenset[str], str]:
    """Parse a trigger string like ``Ctrl+Shift+G`` into a (modifiers, key) pair."""
    parts = trigger.split("+")
    if not parts:
        raise ValueError(f"Invalid shortcut trigger: {trigger!r}")
    key = parts[-1]
    modifiers = frozenset(parts[:-1])
    for mod in modifiers:
        if mod.upper() not in _MODIFIER_NAMES:
            raise ValueError(f"Unknown modifier: {mod!r}")
    if not key or not all(c in _LEGAL_KEY_CHARS for c in key):
        raise ValueError(f"Invalid key: {key!r}")
    return modifiers, key


def format_shortcut_trigger(modifiers: set[str], key: str) -> str:
    """Format a (modifiers, key) pair back into a trigger string like ``Ctrl+Shift+G``."""
    mods = "+".join(sorted(m.upper() for m in modifiers))
    if mods:
        return f"{mods}+{key}"
    return key


def generate_handle_token(prefix: str = "gs") -> str:
    """Generate a random handle token with an optional prefix for portal requests."""
    rand = secrets.token_hex(8)
    return f"{prefix}{rand}"

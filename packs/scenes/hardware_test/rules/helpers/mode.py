"""Shared mode plumbing for the hardware_test scene rules.

Lives in ``rules/helpers/`` (a subpackage the scene scanner skips, like
``tests/``) so it can hold cross-rule constants and lookups without being
mistaken for a rule module.  ``current_mode`` is the single source of truth for
reading the active mode: ``hw_mode`` is seeded into ``initial_data`` so it
normally exists, but the helper still defaults to mode 0 so a missing key
never crashes a rule.
"""

from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass

from engine.state import GameState, Scope

MODE_RGB: Final = 0
MODE_ACCELEROMETER: Final = 1
MODE_IR: Final = 2
MODE_RADIO: Final = 3
MODE_SFX: Final = 4
NUM_MODES: Final = 5

# RGB mode idle effect table: (scope, name)
_RGB_IDLE: Final = (
    (Scope.PERSONAL, "elements.water"),
    (Scope.DIRECTIONAL, "elements.fire"),
    (Scope.Global.MAIN, "elements.lightning"),
    (Scope.Global.BUFF, "elements.earth"),
    (Scope.Global.DEBUFF, "elements.ice"),
)


def current_mode(state: GameState) -> int:
    """Return the active hardware_test mode, defaulting to ``MODE_RGB`` when unseeded."""
    return state.get("hw_mode", 0)

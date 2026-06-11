"""Shared test helpers for the Tag scene rule tests.

``seed_phase`` jumps a freshly-built ``TagState`` directly to a phase
(optionally already-entered), so each rule's tests can exercise the phase
in isolation without replaying the whole phase machine from Ready.
"""

from __future__ import annotations

from engine.state import GameState
from packs.scenes.tag.rules.helpers.tag_state import TagState, tag_state


class StubTimer:
    """Controllable timer for tests that need specific ``state.total`` values."""

    def __init__(self) -> None:
        self.elapsed: float = 0.0
        self.total: float = 0.0

    def update(self) -> None:
        pass  # Caller controls total directly


def seed_phase(state: GameState, phase: str, entered: bool = False) -> TagState:
    """Return the shared ``TagState`` jumped to *phase*.

    If *entered* is ``True``, the phase's one-time entry side-effects are
    treated as already having run (``just_entered`` is ``False``).
    """
    tag = tag_state(state)
    tag.enter(phase)
    if entered:
        tag.mark_entered()
    return tag

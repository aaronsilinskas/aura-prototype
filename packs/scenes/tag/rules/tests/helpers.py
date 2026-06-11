"""Shared test helpers for the Tag scene rule tests.

``seed_phase`` jumps the scene's :class:`PhaseMachine` directly to a phase
(optionally already-entered), returning the shared ``TagState`` so each rule's
tests can exercise the phase in isolation without replaying the whole phase
machine from Ready.
"""

from __future__ import annotations

from engine.phase import PhaseKey
from engine.state import GameState
from packs.scenes.tag.rules.helpers.phases import tag_phase
from packs.scenes.tag.rules.helpers.tag_state import TagState, tag_state


class StubTimer:
    """Controllable timer for tests that need specific ``state.total`` values."""

    def __init__(self) -> None:
        self.elapsed: float = 0.0
        self.total: float = 0.0

    def update(self) -> None:
        pass  # Caller controls total directly


def seed_phase(state: GameState, phase: PhaseKey, entered: bool = False) -> TagState:
    """Jump the scene's phase machine to *phase* and return the shared ``TagState``.

    If *entered* is ``True``, the phase's one-time entry side-effects are
    treated as already having run (the just-entered flag is cleared).
    """
    machine = tag_phase(state)
    machine.enter(phase, state.total)
    if entered:
        machine.take_just_entered()
    return tag_state(state)

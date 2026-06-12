"""Shared test helpers for the hardware_test scene rule tests.

``seed_phase`` jumps the scene's :class:`PhaseMachine` directly to a mode, so
each mode's tests can exercise it in isolation without replaying the whole
mode cycle from RGB.
"""

from __future__ import annotations

from engine.phase import PhaseKey
from engine.state import GameState
from packs.scenes.hardware_test.rules.helpers.phases import hw_phase


class StubTimer:
    """Controllable timer for tests that need specific ``state.total`` values."""

    def __init__(self) -> None:
        self.elapsed: float = 0.0
        self.total: float = 0.0

    def update(self) -> None:
        pass  # Caller controls total directly


def seed_phase(state: GameState, phase: PhaseKey, entered: bool = False) -> None:
    """Jump the scene's phase machine to *phase*.

    If *entered* is ``True``, the phase's one-time entry side-effects are
    treated as already having run (the just-entered flag is cleared).
    """
    machine = hw_phase(state)
    machine.enter(phase, state.total)
    if entered:
        machine.take_just_entered()

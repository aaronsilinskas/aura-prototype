"""RLGL scene Win phase rule.

On entry, plays ``elements.lightning`` at level 7 across the whole device,
adds the win sting, and declares that the phase ends when the sting stops,
moving back to Ready.
"""

from __future__ import annotations

from engine.phase import PhaseRule
from engine.state import GameState, Scope
from packs.scenes.red_light_green_light.rules.helpers.phases import (
    PHASE_READY,
    PHASE_WIN,
    rlgl_phase,
)


class RlglWinRule(PhaseRule):
    """Drives the Win phase: lightning + win sting, then back to Ready."""

    def __init__(self) -> None:
        super().__init__(PHASE_WIN, rlgl_phase)

    def on_enter(self, state: GameState) -> None:
        state.effect_controls.set_effect(Scope.ALL, "elements.lightning", {"level": 7})
        receipt = state.effect_controls.add_effect(Scope.ALL, "scene.win_sting", {})
        self.end_when_stopped(state, receipt, PHASE_READY)


RULE = RlglWinRule()

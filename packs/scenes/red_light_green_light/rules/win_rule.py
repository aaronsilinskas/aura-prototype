"""RLGL scene Win phase rule.

On entry, plays ``elements.lightning`` at level 7 across the whole device and
adds the win sting, storing its receipt as ``win_sting_receipt``. Stays in Win
until the sting's receipt reports stopped, then transitions back to Ready.
"""

from __future__ import annotations

from engine.input import InputEvents
from engine.phase import PhaseRule
from engine.state import GameState, Scope
from packs.scenes.red_light_green_light.rules.helpers.phases import (
    PHASE_READY,
    PHASE_WIN,
    rlgl_phase,
)
from packs.scenes.red_light_green_light.rules.helpers.rlgl_phase_state import rlgl_phase_state


class RlglWinRule(PhaseRule):
    """Drives the Win phase: lightning + win sting, then back to Ready."""

    def __init__(self) -> None:
        super().__init__(PHASE_WIN, rlgl_phase)
        self.on(InputEvents.ButtonAndAcceleration, self._handle)

    def on_enter(self, state: GameState) -> None:
        state.effect_controls.set_effect(Scope.ALL, "elements.lightning", {"level": 7})
        receipt = state.effect_controls.add_effect(Scope.ALL, "scene.win_sting", {})
        rlgl_phase_state(state).win_sting_receipt = receipt

    def _handle(self, event: InputEvents.ButtonAndAcceleration, state: GameState) -> None:
        receipt = rlgl_phase_state(state).win_sting_receipt
        if receipt is not None and receipt.is_stopped():
            self.transition_to(state, PHASE_READY)


RULE = RlglWinRule()

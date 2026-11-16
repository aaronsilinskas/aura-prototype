"""The rule behind both RLGL warning phases, Red Warning and Green Warning.

On entry, shows the warning sting (scaled to the current Game Level's pulse
duration) on ``Scope.NON_AMBIENT`` and declares that the phase ends after that
level's warning duration, moving to the light it warns of.
"""

from __future__ import annotations

from engine.phase import PhaseKey, PhaseRule
from engine.state import GameState, Scope
from packs.scenes.red_light_green_light.rules.helpers.phases import rlgl_phase
from packs.scenes.red_light_green_light.rules.helpers.rlgl_config import rlgl_config
from packs.scenes.red_light_green_light.rules.helpers.rlgl_phase_state import rlgl_phase_state


class RlglWarningRule(PhaseRule):
    """Drives one warning phase: warning sting, then into *next_phase*."""

    def __init__(self, phase: PhaseKey, next_phase: PhaseKey) -> None:
        super().__init__(phase, rlgl_phase)
        self._next_phase = next_phase

    def on_enter(self, state: GameState) -> None:
        level = rlgl_phase_state(state).level
        config = rlgl_config(state)
        state.effect_controls.set_effect(
            Scope.NON_AMBIENT,
            "scene.warning_sting",
            {"pulse_duration": config.warning_pulse_duration(level)},
        )
        self.end_after(state, config.warning_duration(level), self._next_phase)

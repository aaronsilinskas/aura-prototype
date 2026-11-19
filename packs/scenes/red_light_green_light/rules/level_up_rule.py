from __future__ import annotations

from engine.phase import PhaseRule
from engine.state import GameState, Scope
from packs.scenes.red_light_green_light.rules.helpers.phases import (
    PHASE_LEVEL_UP,
    PHASE_RED_WARNING,
    rlgl_phase,
)
from packs.scenes.red_light_green_light.rules.helpers.rlgl_config import rlgl_config
from packs.scenes.red_light_green_light.rules.helpers.rlgl_phase_state import rlgl_phase_state


class RlglLevelUpRule(PhaseRule):
    def __init__(self) -> None:
        super().__init__(PHASE_LEVEL_UP, rlgl_phase)

    def on_enter(self, state: GameState) -> None:
        phase_state = rlgl_phase_state(state)
        level = phase_state.level + 1
        phase_state.level = level
        config = rlgl_config(state)
        state.effect_controls.set_effect(
            Scope.AMBIENT, "basic.progress", {"progress": level / config.max_level}
        )
        state.effect_controls.set_effect(Scope.NON_AMBIENT, "scene.level_up", {})
        self.end_after(state, config.level_up_duration, PHASE_RED_WARNING)


RULE = RlglLevelUpRule()

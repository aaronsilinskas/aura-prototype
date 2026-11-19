from __future__ import annotations

from engine.input import InputEvents
from engine.phase import PhaseRule
from engine.state import GameState, Scope
from packs.scenes.red_light_green_light.rules.helpers.phases import (
    PHASE_READY,
    PHASE_RED_WARNING,
    rlgl_phase,
)
from packs.scenes.red_light_green_light.rules.helpers.rlgl_config import rlgl_config
from packs.scenes.red_light_green_light.rules.helpers.rlgl_phase_state import rlgl_phase_state

TYPE_CHECKING = False

if TYPE_CHECKING:
    from typing import Final

_STARTING_LEVEL: Final = 1


class RlglReadyRule(PhaseRule):
    def __init__(self) -> None:
        super().__init__(PHASE_READY, rlgl_phase)
        self.on(InputEvents.Sensors, self._handle)

    def on_enter(self, state: GameState) -> None:
        state.effect_controls.set_effect(Scope.ALL, "scene.ready", {})

    def _handle(self, event: InputEvents.Sensors, state: GameState) -> None:
        if event.buttons.is_pressed("A") or event.buttons.is_pressed("B"):
            self._start_game(state)

    def _start_game(self, state: GameState) -> None:
        phase_state = rlgl_phase_state(state)
        phase_state.level = _STARTING_LEVEL
        max_level = rlgl_config(state).max_level
        state.effect_controls.set_effect(
            Scope.AMBIENT, "basic.progress", {"progress": _STARTING_LEVEL / max_level}
        )
        self.transition_to(state, PHASE_RED_WARNING)


RULE = RlglReadyRule()

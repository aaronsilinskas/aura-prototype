from __future__ import annotations

from engine.input import InputEvents
from engine.phase import PhaseRule
from engine.state import GameState, Scope
from packs.scenes.tag.rules.helpers.phases import PHASE_READY, PHASE_STARTING, tag_phase


class TagReadyRule(PhaseRule):
    def __init__(self) -> None:
        super().__init__(PHASE_READY, tag_phase)
        self.on(InputEvents.Sensors, self._handle)

    def on_enter(self, state: GameState) -> None:
        state.effect_controls.set_effect(Scope.ALL, "scene.ready", {})
        state.effect_controls.add_effect(Scope.ALL, "scene.ready_shots", {})

    def _handle(self, event: InputEvents.Sensors, state: GameState) -> None:
        if event.buttons.is_pressed("A") or event.buttons.is_pressed("B"):
            self.transition_to(state, PHASE_STARTING)


RULE = TagReadyRule()

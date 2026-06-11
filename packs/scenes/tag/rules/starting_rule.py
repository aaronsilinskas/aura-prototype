"""Tag scene Starting phase rule.

On entry, sets the looping warning-pulse effect once and records its receipt.
Transitions to Playing after ``count x duration`` seconds (RLGL
``warning_duration`` time-counting style — the elapsed phase time from the
shared :class:`PhaseMachine` is compared to the total countdown duration, not
by listening for individual peaks), stopping the pulse on the way out.
"""

from __future__ import annotations

from engine.input import InputEvents
from engine.state import GameState, Scope
from packs.scenes.tag.rules.helpers.phases import PHASE_PLAYING, PHASE_STARTING, tag_phase
from packs.scenes.tag.rules.helpers.tag_config import tag_config
from packs.scenes.tag.rules.helpers.tag_phase_rule import TagPhaseRule
from packs.scenes.tag.rules.helpers.tag_state import tag_state


class TagStartingRule(TagPhaseRule):
    """Drives the Starting phase: warning countdown into Playing."""

    def __init__(self) -> None:
        super().__init__(PHASE_STARTING)
        self.on(InputEvents.ButtonAndAcceleration, self._handle)

    def on_enter(self, state: GameState) -> None:
        config = tag_config(state)
        half = config.warning_pulse_duration / 2
        tag_state(state).warning_receipt = state.effect_controls.set_effect(
            Scope.ALL,
            "scene.warning_pulse",
            {
                "brighten_duration": half,
                "on_duration": 0.0,
                "darken_duration": half,
                "off_duration": 0.0,
            },
        )

    def on_exit(self, state: GameState) -> None:
        state.effect_controls.stop_effect(Scope.ALL)
        tag_state(state).warning_receipt = None

    def _handle(self, event: InputEvents.ButtonAndAcceleration, state: GameState) -> None:
        config = tag_config(state)
        if tag_phase(state).elapsed(state.total) >= config.warning_duration():
            self.transition_to(state, PHASE_PLAYING)


RULE = TagStartingRule()

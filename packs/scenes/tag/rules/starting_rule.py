"""Tag scene Starting phase rule.

On entry, sets the looping warning-pulse effect once and records the start
time. Transitions to Playing after ``count x duration`` seconds (RLGL
``warning_duration`` time-counting style — the elapsed phase time is compared
to the total countdown duration, not by listening for individual peaks), then
stops the pulse.
"""

from __future__ import annotations

from engine.engine import GameRule
from engine.input import InputEvents
from engine.state import GameState, Scope
from packs.scenes.tag.rules.helpers.phases import PHASE_PLAYING, PHASE_STARTING
from packs.scenes.tag.rules.helpers.tag_config import tag_config
from packs.scenes.tag.rules.helpers.tag_state import tag_state


class TagStartingRule(GameRule):
    """Drives the Starting phase: warning countdown into Playing."""

    def __init__(self) -> None:
        self.on(InputEvents.ButtonAndAcceleration, self._handle)

    def _handle(self, event: InputEvents.ButtonAndAcceleration, state: GameState) -> None:
        tag = tag_state(state)
        if tag.phase != PHASE_STARTING:
            return

        config = tag_config(state)

        if tag.take_just_entered():
            duration = config.warning_pulse_duration
            half = duration / 2
            state.effect_controls.set_effect(
                Scope.ALL,
                "scene.warning_pulse",
                {
                    "brighten_duration": half,
                    "on_duration": 0.0,
                    "darken_duration": half,
                    "off_duration": 0.0,
                },
            )
            tag.warning_start = state.total

        if state.total - tag.warning_start >= config.warning_duration():
            state.effect_controls.stop_effect(Scope.ALL)
            tag.enter(PHASE_PLAYING)


RULE = TagStartingRule()

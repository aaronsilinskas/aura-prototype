from __future__ import annotations

from engine.phase import PhaseRule
from engine.state import GameState, Scope
from packs.scenes.tag.rules.helpers.phases import (
    PHASE_PLAYING,
    PHASE_STARTING,
    tag_phase,
)
from packs.scenes.tag.rules.helpers.tag_config import tag_config


class TagStartingRule(PhaseRule):
    """Plays the warning countdown, then moves to Playing.

    The countdown is timed as a whole (``count x duration``) rather than by
    listening for individual pulse peaks.
    """

    def __init__(self) -> None:
        super().__init__(PHASE_STARTING, tag_phase)

    def on_enter(self, state: GameState) -> None:
        config = tag_config(state)
        state.effect_controls.set_effect(
            Scope.ALL,
            "scene.warning_pulse",
            {"pulse_duration": config.warning_pulse_duration},
        )
        self.end_after(state, config.warning_duration(), PHASE_PLAYING)

    def on_exit(self, state: GameState) -> None:
        state.effect_controls.stop_effect(Scope.ALL)


RULE = TagStartingRule()

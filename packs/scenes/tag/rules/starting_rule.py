"""Tag scene Starting phase rule.

On entry, sets the looping warning-pulse effect once and declares that the
phase ends after the countdown, ``count x duration`` seconds (timed as a
whole, not by listening for individual peaks), going to Playing. The pulse is
stopped on the way out.
"""

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
    """Drives the Starting phase: warning countdown into Playing."""

    def __init__(self) -> None:
        super().__init__(PHASE_STARTING, tag_phase)

    def on_enter(self, state: GameState) -> None:
        config = tag_config(state)
        half = config.warning_pulse_duration / 2
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
        self.end_after(state, config.warning_duration(), PHASE_PLAYING)

    def on_exit(self, state: GameState) -> None:
        state.effect_controls.stop_effect(Scope.ALL)


RULE = TagStartingRule()

"""Tag scene Starting phase rule.

On entry, sets the looping warning-pulse effect once and records the start
time. Transitions to Playing after ``count x duration`` seconds (RLGL
``_warning_duration`` time-counting style — the elapsed phase time is compared
to the total countdown duration, not by listening for individual peaks), then
stops the pulse.
"""

from __future__ import annotations

from engine.engine import GameRule
from engine.input import InputEvents
from engine.state import GameState, Scope
from packs.scenes.tag.rules.helpers.phases import (
    DEFAULT_WARNING_PULSE_COUNT,
    DEFAULT_WARNING_PULSE_DURATION,
    KEY_ENTERED,
    KEY_PHASE,
    KEY_WARNING_PULSE_COUNT,
    KEY_WARNING_PULSE_DURATION,
    KEY_WARNING_START,
    PHASE_PLAYING,
    PHASE_STARTING,
)


def _warning_duration(state: GameState) -> float:
    """Return the total countdown duration = pulse count x pulse duration."""
    count = state.get(KEY_WARNING_PULSE_COUNT, DEFAULT_WARNING_PULSE_COUNT)
    duration = state.get(KEY_WARNING_PULSE_DURATION, DEFAULT_WARNING_PULSE_DURATION)
    return count * duration


class TagStartingRule(GameRule):
    """Drives the Starting phase: warning countdown into Playing."""

    def __init__(self) -> None:
        self.on(InputEvents.ButtonAndAcceleration, self._handle)

    def _handle(self, event: InputEvents.ButtonAndAcceleration, state: GameState) -> None:
        phase = state.get(KEY_PHASE, "ready")
        if phase != PHASE_STARTING:
            return

        if not state.get(KEY_ENTERED, False):
            duration = state.get(KEY_WARNING_PULSE_DURATION, DEFAULT_WARNING_PULSE_DURATION)
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
            state.set(KEY_WARNING_START, state.total)
            state.set(KEY_ENTERED, True)

        start = state.get(KEY_WARNING_START, state.total)
        if state.total - start >= _warning_duration(state):
            state.effect_controls.stop_effect(Scope.ALL)
            state.set(KEY_PHASE, PHASE_PLAYING)
            state.set(KEY_ENTERED, False)


RULE = TagStartingRule()

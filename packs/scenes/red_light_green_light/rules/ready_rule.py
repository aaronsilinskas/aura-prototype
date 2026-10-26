"""RLGL scene Ready phase rule.

On entry, plays the scene's "ready" effect across the whole device, replacing
the Game Level's ``Scope.AMBIENT`` progress bar. Any button press starts a new
game at level 1 and transitions to Red Warning.
"""

from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass  # typing not available on all embedded runtimes

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

_STARTING_LEVEL: Final = 1


class RlglReadyRule(PhaseRule):
    """Drives the Ready phase: plays the ready effect, waits for a button press."""

    def __init__(self) -> None:
        super().__init__(PHASE_READY, rlgl_phase)
        self.on(InputEvents.Sensors, self._handle)

    def on_enter(self, state: GameState) -> None:
        state.effect_controls.set_effect(Scope.ALL, "scene.ready", {})

    def _handle(self, event: InputEvents.Sensors, state: GameState) -> None:
        if event.buttons.is_pressed("A") or event.buttons.is_pressed("B"):
            self._start_game(state)

    def _start_game(self, state: GameState) -> None:
        """Initialise a new game at level 1 and transition to Red Warning.

        Sets the Game Level to 1 and starts the ``Scope.AMBIENT`` progress bar at
        ``1 / max_level`` (denominator from ``rlgl_max_level``, default 10).
        """
        phase_state = rlgl_phase_state(state)
        phase_state.level = _STARTING_LEVEL
        max_level = rlgl_config(state).max_level
        state.effect_controls.set_effect(
            Scope.AMBIENT, "basic.progress", {"progress": _STARTING_LEVEL / max_level}
        )
        self.transition_to(state, PHASE_RED_WARNING)


RULE = RlglReadyRule()

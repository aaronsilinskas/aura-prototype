"""RLGL scene Ready phase rule.

On entry, plays the scene's "ready" effect across the whole device and clears
the Game Level's ``Scope.AMBIENT`` progress bar receipt -- the one place Game
Level's lifecycle ends, so it survives every mid-game phase transition. Any
button press starts a new game at level 1 and transitions to Red Warning.
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
    RLGL_MACHINE_KEY,
)
from packs.scenes.red_light_green_light.rules.helpers.rlgl_config import rlgl_config
from packs.scenes.red_light_green_light.rules.helpers.rlgl_phase_state import rlgl_phase_state

_STARTING_LEVEL: Final = 1


class RlglReadyRule(PhaseRule):
    """Drives the Ready phase: plays the ready effect, waits for a button press."""

    def __init__(self) -> None:
        super().__init__(PHASE_READY, RLGL_MACHINE_KEY, PHASE_READY)
        self.on(InputEvents.ButtonAndAcceleration, self._handle)

    def on_enter(self, state: GameState) -> None:
        state.effect_controls.set_effect(Scope.ALL, "scene.ready", {})
        phase_state = rlgl_phase_state(state)
        if phase_state.level_receipt is not None:
            phase_state.level_receipt.stop()
            phase_state.level_receipt = None

    def _handle(self, event: InputEvents.ButtonAndAcceleration, state: GameState) -> None:
        if event.buttons.is_pressed("A") or event.buttons.is_pressed("B"):
            self._start_game(state)

    def _start_game(self, state: GameState) -> None:
        """Initialise a new game at level 1 and transition to Red Warning.

        Sets the Game Level to 1, starts the ``Scope.AMBIENT`` progress bar at
        ``1 / max_level`` (denominator from ``rlgl_max_level``, default 10), and
        stores the receipt as ``level_receipt``. The receipt persists across all
        mid-game phase transitions and is only cleared when Ready is re-entered.
        """
        phase_state = rlgl_phase_state(state)
        phase_state.level = _STARTING_LEVEL
        max_level = rlgl_config(state).max_level
        receipt = state.effect_controls.set_effect(
            Scope.AMBIENT, "basic.progress", {"progress": _STARTING_LEVEL / max_level}
        )
        phase_state.level_receipt = receipt
        self.transition_to(state, PHASE_RED_WARNING)


RULE = RlglReadyRule()

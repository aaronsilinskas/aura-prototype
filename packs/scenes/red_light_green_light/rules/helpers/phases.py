"""Phase keys and the typed phase-machine accessor for the ``red_light_green_light`` scene."""

from __future__ import annotations

from engine.phase import PhaseKey, PhaseSlot

TYPE_CHECKING = False

if TYPE_CHECKING:
    from typing import Final


PHASE_READY: Final = PhaseKey("ready")
PHASE_RED_WARNING: Final = PhaseKey("red_warning")
PHASE_RED: Final = PhaseKey("red")
PHASE_GREEN_WARNING: Final = PhaseKey("green_warning")
PHASE_GREEN: Final = PhaseKey("green")
PHASE_LEVEL_UP: Final = PhaseKey("level_up")
PHASE_WIN: Final = PhaseKey("win")
PHASE_GAME_OVER: Final = PhaseKey("game_over")

rlgl_phase: PhaseSlot = PhaseSlot("rlgl_phase", PHASE_READY)

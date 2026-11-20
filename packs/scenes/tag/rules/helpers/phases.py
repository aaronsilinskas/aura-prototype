"""Phase keys and the typed phase-machine accessor for the ``tag`` scene."""

from __future__ import annotations

from engine.phase import PhaseKey, PhaseSlot

TYPE_CHECKING = False

if TYPE_CHECKING:
    from typing import Final


PHASE_READY: Final = PhaseKey("ready")
PHASE_STARTING: Final = PhaseKey("starting")
PHASE_PLAYING: Final = PhaseKey("playing")
PHASE_GAME_OVER: Final = PhaseKey("game_over")

tag_phase: PhaseSlot = PhaseSlot("tag_phase", PHASE_READY)

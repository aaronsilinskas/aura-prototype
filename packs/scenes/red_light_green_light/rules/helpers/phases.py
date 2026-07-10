"""Phase keys and the typed phase-machine accessor for the ``red_light_green_light`` scene.

The RLGL scene is an eight-phase state machine -- Ready -> Red Warning -> Red ->
Green Warning -> Green -> (Level Up | Win) -> Game Over -- driven by the
reusable phase-machine primitive in :mod:`engine.phase`. This module owns the
scene's named :class:`PhaseKey` instances and the single :data:`rlgl_phase`
:class:`~engine.phase.PhaseSlot` -- see that class's docstring for how every
RLGL rule and this module-level reference come to share one
:class:`~engine.phase.PhaseMachine`.

Because :class:`PhaseKey` compares by identity, these module-level singletons
are the *only* tokens that match the machine's current phase; a bare string
literal never will. All eight phases share the one machine held by
:data:`rlgl_phase`.
"""

from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass  # typing not available on all embedded runtimes

from engine.phase import PhaseKey, PhaseSlot

# ---------------------------------------------------------------------------
# Phase keys -- identity-typed singletons owned by the scene
# ---------------------------------------------------------------------------

PHASE_READY: Final = PhaseKey("ready")
PHASE_RED_WARNING: Final = PhaseKey("red_warning")
PHASE_RED: Final = PhaseKey("red")
PHASE_GREEN_WARNING: Final = PhaseKey("green_warning")
PHASE_GREEN: Final = PhaseKey("green")
PHASE_LEVEL_UP: Final = PhaseKey("level_up")
PHASE_WIN: Final = PhaseKey("win")
PHASE_GAME_OVER: Final = PhaseKey("game_over")

rlgl_phase: PhaseSlot = PhaseSlot("rlgl_phase", PHASE_READY)

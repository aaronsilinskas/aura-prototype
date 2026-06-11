"""Phase keys and the typed phase-machine accessor for the ``red_light_green_light`` scene.

The RLGL scene is an eight-phase state machine -- Ready -> Red Warning -> Red ->
Green Warning -> Green -> (Level Up | Win) -> Game Over -- driven by the
reusable phase-machine primitive in :mod:`engine.phase`. This module owns the
scene's named :class:`PhaseKey` instances and the single :func:`rlgl_phase`
accessor that fixes the machine key and the initial phase, so every RLGL rule
reaches the same machine the same way.

Because :class:`PhaseKey` compares by identity, these module-level singletons
are the *only* tokens that match the machine's current phase; a bare string
literal never will. ``PhaseRule``s point their ``_machine`` hook at
:func:`rlgl_phase`, and all eight phases share the one machine cached under
:data:`RLGL_MACHINE_KEY`.
"""

from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass  # typing not available on all embedded runtimes

from engine.phase import PhaseKey, PhaseMachine, phase_machine
from engine.state import GameState

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

RLGL_MACHINE_KEY: Final = "rlgl_phase"


def rlgl_phase(state: GameState) -> PhaseMachine:
    """Return the RLGL scene's :class:`PhaseMachine`, building it on first use.

    Fixes the generic :func:`phase_machine` accessor to this scene's machine
    key and :data:`PHASE_READY` initial phase, so every RLGL rule shares one
    machine that starts in Ready.
    """
    return phase_machine(state, RLGL_MACHINE_KEY, PHASE_READY)

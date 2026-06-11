"""Phase keys and the typed phase-machine accessor for the ``tag`` scene.

The Tag scene is a four-phase state machine — Ready -> Starting -> Playing ->
Game Over — driven by the reusable phase-machine primitive in
:mod:`engine.phase`. This module owns the scene's named :class:`PhaseKey`
instances and the single :func:`tag_phase` accessor that fixes the machine key
and the initial phase, so every Tag rule reaches the same machine the same way.

Because :class:`PhaseKey` compares by identity, these module-level singletons
are the *only* tokens that match the machine's current phase; a bare string
literal never will. ``PhaseRule``s point their ``_machine`` hook at
:func:`tag_phase`, and the four lifecycle phases share the one machine cached
under :data:`_MACHINE_KEY`.
"""

from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass  # typing not available on all embedded runtimes

from engine.phase import PhaseKey, PhaseMachine, phase_machine
from engine.state import GameState

# ---------------------------------------------------------------------------
# Phase keys — identity-typed singletons owned by the scene
# ---------------------------------------------------------------------------

PHASE_READY: Final = PhaseKey("ready")
PHASE_STARTING: Final = PhaseKey("starting")
PHASE_PLAYING: Final = PhaseKey("playing")
PHASE_GAME_OVER: Final = PhaseKey("game_over")

TAG_MACHINE_KEY: Final = "tag_phase"


def tag_phase(state: GameState) -> PhaseMachine:
    """Return the Tag scene's :class:`PhaseMachine`, building it on first use.

    Fixes the generic :func:`phase_machine` accessor to this scene's machine
    key and :data:`PHASE_READY` initial phase, so every Tag rule shares one
    machine that starts in Ready.
    """
    return phase_machine(state, TAG_MACHINE_KEY, PHASE_READY)

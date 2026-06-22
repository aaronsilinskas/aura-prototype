"""Phase keys and the typed phase-machine accessor for the ``tag`` scene.

The Tag scene is a four-phase state machine — Ready -> Starting -> Playing ->
Game Over — driven by the reusable phase-machine primitive in
:mod:`engine.phase`. This module owns the scene's named :class:`PhaseKey`
instances and the single :data:`tag_phase` :class:`~engine.state.StateSlot`
that fixes the machine key and the initial phase, so every Tag rule reaches
the same machine the same way.

Because :class:`PhaseKey` compares by identity, these module-level singletons
are the *only* tokens that match the machine's current phase; a bare string
literal never will. The four lifecycle phases share the one machine cached
under :data:`TAG_MACHINE_KEY`.
"""

from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass  # typing not available on all embedded runtimes

from engine.phase import PhaseKey, PhaseMachine
from engine.state import StateSlot

# ---------------------------------------------------------------------------
# Phase keys — identity-typed singletons owned by the scene
# ---------------------------------------------------------------------------

PHASE_READY: Final = PhaseKey("ready")
PHASE_STARTING: Final = PhaseKey("starting")
PHASE_PLAYING: Final = PhaseKey("playing")
PHASE_GAME_OVER: Final = PhaseKey("game_over")

TAG_MACHINE_KEY: Final = "tag_phase"

tag_phase: StateSlot = StateSlot(TAG_MACHINE_KEY, lambda s: PhaseMachine(PHASE_READY), PhaseMachine)

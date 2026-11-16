"""Phase keys and the typed phase-machine accessor for the ``tag`` scene.

The Tag scene is a four-phase state machine — Ready -> Starting -> Playing ->
Game Over — driven by the reusable phase-machine primitive in
:mod:`engine.phase`. This module owns the scene's named :class:`PhaseKey`
instances and the single :data:`tag_phase` :class:`~engine.phase.PhaseSlot` —
see that class's docstring for how every Tag rule and this module-level
reference come to share one :class:`~engine.phase.PhaseMachine`.

Because :class:`PhaseKey` compares by identity, these module-level singletons
are the *only* tokens that match the machine's current phase; a bare string
literal never will. The four lifecycle phases share the one machine held by
:data:`tag_phase`.
"""

from __future__ import annotations

from engine.phase import PhaseKey, PhaseSlot

TYPE_CHECKING = False

if TYPE_CHECKING:
    from typing import Final

# ---------------------------------------------------------------------------
# Phase keys — identity-typed singletons owned by the scene
# ---------------------------------------------------------------------------

PHASE_READY: Final = PhaseKey("ready")
PHASE_STARTING: Final = PhaseKey("starting")
PHASE_PLAYING: Final = PhaseKey("playing")
PHASE_GAME_OVER: Final = PhaseKey("game_over")

tag_phase: PhaseSlot = PhaseSlot("tag_phase", PHASE_READY)

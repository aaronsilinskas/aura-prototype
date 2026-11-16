"""``RlglPhaseState`` -- mutable Game Level and music state for Red Light Green Light.

Groups the Game Level and the in-flight music receipt into a single mutable
object, mirroring the ``RlglConfig`` (``rlgl_config``) and ``RlglMotion``
(``rlgl_motion``) accessors.

Phase and phase-start bookkeeping now live on the shared ``PhaseMachine``
(``rlgl_phase``, see ``phases.py``); this object holds only the state that
survives a phase transition -- Game Level and its ``Scope.AMBIENT`` progress
bar persist across mid-game phase transitions and are reset only on entering
Ready.

``rlgl_phase_state`` is a :class:`engine.state.StateSlot` callable accessor:
it lazily builds the object on first use and caches it under a single
``GameState`` key.
"""

from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass

from engine.state import EffectReceipt, StateSlot

_PHASE_STATE_KEY: Final = "rlgl_phase_state"


class RlglPhaseState:
    """Mutable Game Level and music state for the RLGL scene.

    ``music_receipt`` is a nullable ``EffectReceipt``, stopped and cleared by
    :meth:`stop_music`, called from each music-playing phase's ``on_exit`` so
    a looping music effect can never leak across a phase transition.
    """

    __slots__ = (
        "level",
        "music_receipt",
    )

    def __init__(self) -> None:
        self.level: int = 1
        self.music_receipt: EffectReceipt | None = None

    def stop_music(self) -> None:
        """Stop and clear ``music_receipt`` (a no-op if none is set)."""
        if self.music_receipt is not None:
            self.music_receipt.stop()
            self.music_receipt = None


rlgl_phase_state = StateSlot(_PHASE_STATE_KEY, lambda s: RlglPhaseState(), RlglPhaseState)

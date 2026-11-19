from __future__ import annotations

from engine.state import EffectReceipt, StateSlot

TYPE_CHECKING = False

if TYPE_CHECKING:
    from typing import Final

_PHASE_STATE_KEY: Final = "rlgl_phase_state"


class RlglPhaseState:
    """Game Level and music state that survives phase transitions.

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
        if self.music_receipt is not None:
            self.music_receipt.stop()
            self.music_receipt = None


rlgl_phase_state = StateSlot(_PHASE_STATE_KEY, lambda s: RlglPhaseState(), RlglPhaseState)

"""``RlglPhaseState`` -- mutable Game Level and receipt state for Red Light Green Light.

Groups the Game Level and the three in-flight effect receipts (music, level,
win sting) that previously lived as loose ``rlgl_*`` keys in ``GameState`` into
a single mutable object, mirroring the ``RlglConfig`` (``rlgl_config``) and
``RlglMotion`` (``rlgl_motion``) accessors introduced for #354 and #356.

Phase and phase-start bookkeeping now live on the shared ``PhaseMachine``
(``rlgl_phase``, see ``phases.py``); this object holds only the state that
survives a phase transition -- Game Level and its ``Scope.AMBIENT`` progress
bar persist across mid-game phase transitions and are reset only on entering
Ready.

``rlgl_phase_state(state)`` is the get-or-create accessor: it lazily builds
the object on first use and caches it under a single ``GameState`` key.
"""

from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass

from engine.state import EffectReceipt, GameState

_PHASE_STATE_KEY: Final = "rlgl_phase_state"


class RlglPhaseState:
    """Mutable Game Level and receipt state for the RLGL scene.

    ``music_receipt``, ``level_receipt``, and ``win_sting_receipt`` are
    nullable ``EffectReceipt`` fields. ``level_receipt`` is cleared on
    entering Ready and ``win_sting_receipt`` is polled for
    :meth:`EffectReceipt.is_stopped`; both are managed by explicit assignment
    in the owning phase rules' ``on_enter``/``on_exit``. ``music_receipt`` is
    stopped and cleared by :meth:`stop_music`, called from each music-playing
    phase's ``on_exit`` so a looping music effect can never leak across a
    phase transition.
    """

    __slots__ = (
        "level",
        "level_receipt",
        "music_receipt",
        "win_sting_receipt",
    )

    def __init__(self) -> None:
        self.level: int = 1
        self.music_receipt: EffectReceipt | None = None
        self.level_receipt: EffectReceipt | None = None
        self.win_sting_receipt: EffectReceipt | None = None

    def stop_music(self) -> None:
        """Stop and clear ``music_receipt`` (a no-op if none is set)."""
        if self.music_receipt is not None:
            self.music_receipt.stop()
            self.music_receipt = None


def rlgl_phase_state(state: GameState) -> RlglPhaseState:
    """Return the cached :class:`RlglPhaseState`, building and caching it on first use."""
    if not state.has(_PHASE_STATE_KEY):
        state.set(_PHASE_STATE_KEY, RlglPhaseState())
    return state.get_or_none(_PHASE_STATE_KEY, RlglPhaseState)  # type: ignore[return-value]

"""``RlglPhaseState`` — mutable phase/level/receipt state for Red Light Green Light.

Groups the current phase, phase-start time, Game Level, and the three
in-flight effect receipts (music, level, win sting) that previously lived as
loose ``rlgl_*`` keys in ``GameState`` into a single mutable object, mirroring
the ``RlglConfig`` (``rlgl_config``) and ``RlglMotion`` (``rlgl_motion``)
accessors introduced for #354 and #356.

``rlgl_phase_state(state)`` is the get-or-create accessor: it lazily builds
the object on first use and caches it under a single ``GameState`` key. The
rule detects "object was just created" via ``state.has(_PHASE_STATE_KEY)``
*before* calling the accessor, so the Ready entry effects fire exactly once
on creation -- the object itself never touches ``effect_controls``.
"""

from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass

from engine.state import EffectReceipt, GameState

_PHASE_STATE_KEY: Final = "rlgl_phase_state"

PHASE_READY: Final = "ready"


class RlglPhaseState:
    """Mutable phase/level/receipt state for the RLGL scene.

    ``music_receipt``, ``level_receipt``, and ``win_sting_receipt`` are
    nullable ``EffectReceipt`` fields. ``level_receipt`` is cleared on
    entering Ready and ``win_sting_receipt`` is polled for
    :meth:`EffectReceipt.is_stopped`; both are managed by explicit assignment
    in the rule's ``_enter_*`` helpers. ``music_receipt`` is stopped and
    cleared by :meth:`stop_music`, called from :meth:`enter` so a looping
    music effect can never leak across a phase transition.
    """

    __slots__ = (
        "level",
        "level_receipt",
        "music_receipt",
        "phase",
        "phase_start",
        "win_sting_receipt",
    )

    def __init__(self) -> None:
        self.phase: str = PHASE_READY
        self.phase_start: float = 0.0
        self.level: int = 1
        self.music_receipt: EffectReceipt | None = None
        self.level_receipt: EffectReceipt | None = None
        self.win_sting_receipt: EffectReceipt | None = None

    def enter(self, phase: str, now: float) -> None:
        """Set ``phase`` and ``phase_start`` to ``now``, and stop/clear any music.

        Every ``_enter_*`` helper calls this first, so a looping music effect
        from the previous phase can never leak into the next one.
        """
        self.phase = phase
        self.phase_start = now
        self.stop_music()

    def elapsed(self, now: float) -> float:
        """Return the time elapsed since :attr:`phase_start`."""
        return now - self.phase_start

    def stop_music(self) -> None:
        """Stop and clear ``music_receipt`` (a no-op if none is set)."""
        if self.music_receipt is not None:
            self.music_receipt.stop()
            self.music_receipt = None


def rlgl_phase_state(state: GameState) -> RlglPhaseState:
    """Return the cached :class:`RlglPhaseState`, building and caching it on first use."""
    if not state.has(_PHASE_STATE_KEY):
        state.set(_PHASE_STATE_KEY, RlglPhaseState())
    return state.get(_PHASE_STATE_KEY, None)


def is_phase_state_initialized(state: GameState) -> bool:
    """Return ``True`` if :func:`rlgl_phase_state` has already built and cached its object.

    The rule calls this *before* :func:`rlgl_phase_state` to detect the
    first-tick bootstrap: when ``False``, the Ready entry effects must fire
    once after the object is created.
    """
    return state.has(_PHASE_STATE_KEY)

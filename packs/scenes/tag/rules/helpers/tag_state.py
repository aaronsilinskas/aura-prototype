"""``TagState`` — the residual flat per-tick state for the Tag scene.

Phase mechanics (the current phase, the first-tick entry flag, and the
phase-start clock) now live in the scene's :class:`PhaseMachine`, reached via
:func:`packs.scenes.tag.rules.helpers.phases.tag_phase`. What remains here is
the flat gameplay bookkeeping that the phase machine deliberately does not
own: hitpoints, the self-deafen deadline, and the in-flight per-phase
``EffectReceipt``s.

Each owning rule clears the fields it owns in its ``on_exit``: the Playing rule
owns ``progress_receipt`` (shared with the hit reactor) and the Game Over rule
owns ``game_over_receipt``. ``tag_state(state)`` is the get-or-create accessor,
mirroring ``tag_config(state)``.
"""

from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass

from engine.state import EffectReceipt, GameState

_STATE_KEY: Final = "tag_state"


class TagState:
    """Mutable flat gameplay state shared by the Tag rules.

    Fetched once per tick by the rules that need it via :func:`tag_state`.
    Receipts are typed nullable fields (``EffectReceipt | None``) rather than
    opaque ``GameState`` keys, so no runtime ``isinstance`` validation is
    needed to read them back. Phase, the entry flag, and the phase-start clock
    are *not* here — they belong to the :class:`PhaseMachine`.
    """

    __slots__ = (
        "deafen_until",
        "game_over_receipt",
        "hitpoints",
        "progress_receipt",
        "warning_receipt",
    )

    def __init__(self) -> None:
        self.hitpoints = 0
        self.deafen_until = 0.0
        self.progress_receipt: EffectReceipt | None = None
        self.warning_receipt: EffectReceipt | None = None
        self.game_over_receipt: EffectReceipt | None = None


def tag_state(state: GameState) -> TagState:
    """Return the cached :class:`TagState`, building and caching it on first use."""
    if not state.has(_STATE_KEY):
        state.set(_STATE_KEY, TagState())
    return state.get(_STATE_KEY, None)

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


class ShotState:
    """Shot-related gameplay state: ammo, shot-cooldown, and reload tracking.

    ``reload_started_at`` is ``None`` when not reloading, else the
    ``state.total`` timestamp the current hold-to-reload began.
    ``reload_receipt`` is the in-flight ``scene.reload`` effect on
    ``Scope.Global.BUFF``, if any.
    """

    __slots__ = (
        "ammo",
        "last_shot_at",
        "reload_receipt",
        "reload_started_at",
    )

    def __init__(self) -> None:
        self.ammo = 0
        self.last_shot_at = float("-inf")
        self.reload_started_at: float | None = None
        self.reload_receipt: EffectReceipt | None = None


class TagState:
    """Mutable flat gameplay state shared by the Tag rules.

    Fetched once per tick by the rules that need it via :func:`tag_state`.
    Receipts are typed nullable fields (``EffectReceipt | None``) rather than
    opaque ``GameState`` keys, so no runtime ``isinstance`` validation is
    needed to read them back. Phase, the entry flag, and the phase-start clock
    are *not* here — they belong to the :class:`PhaseMachine`.
    """

    __slots__ = (
        "ammo_receipt",
        "deafen_until",
        "game_over_receipt",
        "hitpoints",
        "progress_receipt",
        "shot",
    )

    def __init__(self) -> None:
        self.hitpoints = 0
        self.deafen_until = 0.0
        self.progress_receipt: EffectReceipt | None = None
        self.game_over_receipt: EffectReceipt | None = None
        self.ammo_receipt: EffectReceipt | None = None
        self.shot = ShotState()


def tag_state(state: GameState) -> TagState:
    """Return the cached :class:`TagState`, building and caching it on first use."""
    if not state.has(_STATE_KEY):
        state.set(_STATE_KEY, TagState())
    return state.get_or_none(_STATE_KEY, TagState)  # type: ignore[return-value]

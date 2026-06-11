"""``TagState`` — mutable per-tick phase-machine state for the Tag scene.

Groups the phase, hitpoints, warning/deafen bookkeeping, and per-phase
``EffectReceipt``s that previously lived as loose ``tag_*`` keys in
``GameState`` into a single mutable object shared by all five Tag rules
(``ready``, ``starting``, ``playing``, ``hit``, ``game_over``).

The shared "entered" flag is folded into atomic methods: :meth:`enter` sets
the phase and resets the flag in one operation, and :meth:`take_just_entered`
returns whether this is the first tick of the phase and clears the flag in
one operation. Because all five rules share one ``TagState`` instance and
these transitions are atomic on it, the alphabetical-dispatch
order-independence contract is preserved regardless of which rule performs
the transition.

``tag_state(state)`` is the get-or-create accessor: it lazily builds the
object on first use and caches it under a single ``GameState`` key, mirroring
the ``tag_config(state)`` accessor introduced for :class:`TagConfig`.
"""

from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass

from engine.state import EffectReceipt, GameState
from packs.scenes.tag.rules.helpers.phases import PHASE_READY

_STATE_KEY: Final = "tag_state"


class TagState:
    """Mutable phase-machine state shared by all Tag rules.

    Fetched once per tick by every rule via :func:`tag_state`. Receipts are
    typed nullable fields (``EffectReceipt | None``) rather than opaque
    ``GameState`` keys, so no runtime ``isinstance`` validation is needed to
    read them back.
    """

    __slots__ = (
        "_just_entered",
        "deafen_until",
        "game_over_receipt",
        "hitpoints",
        "phase",
        "progress_receipt",
        "warning_receipt",
        "warning_start",
    )

    def __init__(self) -> None:
        self.phase = PHASE_READY
        self._just_entered = True
        self.hitpoints = 0
        self.warning_start = 0.0
        self.deafen_until = 0.0
        self.progress_receipt: EffectReceipt | None = None
        self.warning_receipt: EffectReceipt | None = None
        self.game_over_receipt: EffectReceipt | None = None

    def take_just_entered(self) -> bool:
        """Return ``True`` if this is the first tick of the current phase, and clear the flag.

        Atomically combines the old ``just_entered`` check with
        ``mark_entered()``: a rule calls this once per tick to both test and
        consume the one-time entry signal, so there is no separate
        "mark entered" step to forget.
        """
        was_just_entered = self._just_entered
        self._just_entered = False
        return was_just_entered

    def enter(self, phase: str) -> None:
        """Atomically transition to *phase* and mark it as not-yet-entered.

        Replaces the previous two-step ``state.set(KEY_PHASE, ...)`` +
        ``state.set(KEY_ENTERED, False)`` pattern with a single operation on
        the shared object, so no other rule can observe an inconsistent
        phase/entered pairing between the two writes.
        """
        self.phase = phase
        self._just_entered = True


def tag_state(state: GameState) -> TagState:
    """Return the cached :class:`TagState`, building and caching it on first use."""
    if not state.has(_STATE_KEY):
        state.set(_STATE_KEY, TagState())
    return state.get(_STATE_KEY, None)

from __future__ import annotations

from engine.state import EffectReceipt, StateSlot

TYPE_CHECKING = False

if TYPE_CHECKING:
    from typing import Final

_STATE_KEY: Final = "tag_state"


class ShotState:
    """``reload_started_at`` is ``None`` when not reloading, else the
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
    """Gameplay state shared by the Tag rules; phase state lives in the :class:`PhaseMachine`.

    Receipts are typed nullable fields (``EffectReceipt | None``) rather than
    opaque ``GameState`` keys, so no runtime ``isinstance`` validation is
    needed to read them back. The Playing rule owns ``hitpoints_receipt``,
    which the hit rule re-issues, and clears it and the shot receipts in its
    ``on_exit``.
    """

    __slots__ = (
        "hitpoints",
        "hitpoints_receipt",
        "shot",
    )

    def __init__(self) -> None:
        self.hitpoints = 0
        self.hitpoints_receipt: EffectReceipt | None = None
        self.shot = ShotState()


tag_state = StateSlot(_STATE_KEY, lambda s: TagState(), TagState)

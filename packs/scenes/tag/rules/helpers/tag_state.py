from __future__ import annotations

from engine.state import EffectReceipt, StateSlot

TYPE_CHECKING = False

if TYPE_CHECKING:
    from typing import Final

_STATE_KEY: Final = "tag_state"


class ReloadHold:
    """A hold-to-reload in progress: when it began and its ``scene.reload`` effect.

    *started_at* is the ``state.total`` timestamp the hold began; *receipt*
    is the ``scene.reload`` effect on ``Scope.Global.BUFF``.
    """

    __slots__ = ("receipt", "started_at")

    def __init__(self, started_at: float, receipt: EffectReceipt) -> None:
        self.started_at = started_at
        self.receipt = receipt


class ShotState:
    """Ammo, shot-cooldown and reload tracking; ``reload`` is ``None`` when not reloading."""

    __slots__ = (
        "ammo",
        "last_shot_at",
        "reload",
    )

    def __init__(self) -> None:
        self.ammo = 0
        self.last_shot_at = float("-inf")
        self.reload: ReloadHold | None = None


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

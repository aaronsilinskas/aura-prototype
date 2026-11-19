from __future__ import annotations

from engine.state import EffectReceipt, StateSlot

TYPE_CHECKING = False

if TYPE_CHECKING:
    from typing import Final


class Flash:
    """A receipt paired with the time it started, expiring after a duration.

    ``receipt`` is ``None`` until :meth:`restart` is called; an unstarted
    flash is never :meth:`expired`.
    """

    __slots__ = ("receipt", "start_time")

    def __init__(self) -> None:
        self.receipt: EffectReceipt | None = None
        self.start_time: float = 0.0

    def restart(self, now: float, receipt: EffectReceipt) -> None:
        self.receipt = receipt
        self.start_time = now

    def expired(self, now: float, duration: float) -> bool:
        if self.receipt is None:
            return False
        return now - self.start_time > duration


ir_flash: Final = StateSlot("ir_flash", lambda s: Flash(), Flash)
radio_flash: Final = StateSlot("radio_flash", lambda s: Flash(), Flash)

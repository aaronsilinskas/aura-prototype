"""``Flash`` — receipt + start-time bookkeeping for a timed hardware_test flash.

``ir_flash`` and ``radio_flash`` are :class:`~engine.state.StateSlot` callables
that own the get-or-create pattern for each flash; the slot's ``.key``
attribute is the canonical state key used for ``state.delete`` / ``state.has``
operations.
"""

from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass

from engine.state import EffectReceipt, StateSlot


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
        """Begin tracking *receipt*, started at time *now*."""
        self.receipt = receipt
        self.start_time = now

    def expired(self, now: float, duration: float) -> bool:
        """Return ``True`` if a started flash has been running longer than *duration*."""
        if self.receipt is None:
            return False
        return now - self.start_time > duration


ir_flash: Final = StateSlot("ir_flash", lambda s: Flash(), Flash)
radio_flash: Final = StateSlot("radio_flash", lambda s: Flash(), Flash)

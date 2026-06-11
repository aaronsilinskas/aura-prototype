"""``Flash`` — receipt + start-time bookkeeping for a timed hardware_test flash.

The IR and radio receive paths each start a "flash" effect (a white solid)
and need to know when to expire it and restore the idle effect. Both paths
previously duplicated a "receipt + start timestamp, expires after a fixed
duration" pattern as loose ``GameState`` keys; ``Flash`` collapses that into a
single value object that ``HwTestModeRule._check_flash_expiry`` can drive
identically for both flashes.
"""

from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass

from engine.state import EffectReceipt, GameState

IR_FLASH_KEY: Final = "ir_flash"
RADIO_FLASH_KEY: Final = "radio_flash"


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


def flash(state: GameState, key: str) -> Flash:
    """Return the cached :class:`Flash` for *key*, building and caching it on first use."""
    if not state.has(key):
        state.set(key, Flash())
    return state.get(key, None)

import time


class Timer:
    """Tracks elapsed time per update and cumulative total time.

    Call `update()` each loop tick to advance the timer.
    """

    __slots__ = ["_last", "elapsed", "total"]

    def __init__(self) -> None:
        self.elapsed: float = 0.0
        self.total: float = 0.0
        self._last: float = time.monotonic()

    def update(self) -> None:
        """Advance the timer by the time elapsed since the last call."""
        now = time.monotonic()
        self.elapsed = now - self._last
        self.total += self.elapsed
        self._last = now

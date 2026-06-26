from __future__ import annotations

import time

from engine.engine import GameRule
from engine.input import InputEvents
from engine.state import GameState

try:
    from collections.abc import Callable
except ImportError:
    pass


_DEFAULT_ENABLED_KEY = "fps_logging_enabled"


class FpsLoggerRule(GameRule):
    """Prints FPS to the console once per second."""

    __slots__ = ["_clock", "_enabled_key", "_frames", "_output", "_window_start"]

    def __init__(
        self,
        output: Callable[[str], None] = lambda s: print(s),
        clock: Callable[[], float] = time.monotonic,
        enabled_key: str = _DEFAULT_ENABLED_KEY,
    ) -> None:
        self._output = output
        self._clock = clock
        self._enabled_key = enabled_key
        self._frames: int = 0
        self._window_start: float = clock()
        self.on(InputEvents.ButtonAndAcceleration, self._handle)

    def _handle(self, event: InputEvents.ButtonAndAcceleration, state: GameState) -> None:
        if not state.get(self._enabled_key, False):
            return
        self._frames += 1
        now = self._clock()
        elapsed = now - self._window_start
        if elapsed >= 3.0:
            self._output("FPS: " + str(self._frames / elapsed))
            self._frames = 0
            self._window_start = now


RULE = FpsLoggerRule()

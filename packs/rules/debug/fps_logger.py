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
    """Prints the average frame rate to the console every few seconds.

    Set the state key (default ``"fps_logging_enabled"``) to ``True`` in a
    scene's ``initial_data`` to enable logging for that scene.
    """

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
        self.on(InputEvents.Sensors, self._handle)

    def _handle(self, event: InputEvents.Sensors, state: GameState) -> None:
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

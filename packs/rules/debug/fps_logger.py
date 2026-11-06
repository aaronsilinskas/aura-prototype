from __future__ import annotations

import time

from engine.engine import GameRule
from engine.input import InputEvents
from engine.state import GameState
from packs.rules.debug import NAMESPACE

try:
    from collections.abc import Callable
except ImportError:
    pass


class FpsLoggerRule(GameRule):
    """Prints the average frame rate to the console every few seconds.

    Off by default. Set the ``debug`` pack's ``fps_logging_enabled`` Setting to
    ``true`` in a scene's pack reference to log that scene's frame rate.
    """

    __slots__ = ["_clock", "_frames", "_output", "_window_start"]

    def __init__(
        self,
        output: Callable[[str], None] = lambda s: print(s),
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._output = output
        self._clock = clock
        self._frames: int = 0
        self._window_start: float = clock()
        self.on(InputEvents.Sensors, self._handle)

    def _handle(self, event: InputEvents.Sensors, state: GameState) -> None:
        if not state.settings.get_bool(NAMESPACE, "fps_logging_enabled"):
            return
        self._frames += 1
        now = self._clock()
        elapsed = now - self._window_start
        if elapsed >= 3.0:
            self._output("FPS: " + str(self._frames / elapsed))
            self._frames = 0
            self._window_start = now


RULE = FpsLoggerRule()

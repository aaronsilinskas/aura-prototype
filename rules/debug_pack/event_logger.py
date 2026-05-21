from __future__ import annotations

try:
    from collections.abc import Callable
except ImportError:
    pass

from engine.engine import GameRule, GameState, Version
from engine.events import Event

_VERSION: Version = Version(1, 0)


class EventLoggerRule(GameRule):
    """Logs every received event along with all its attributes."""

    __slots__ = ("_output",)

    def __init__(self, output: Callable[[str], None] = lambda s: print(s)) -> None:
        super().__init__("debug.event_logger", _VERSION)
        self._output = output

    def handle_event(self, event: Event, state: GameState) -> None:
        parts = []
        for cls in type(event).__mro__:
            for slot in getattr(cls, "__slots__", ()):
                if slot not in ("group", "name"):
                    parts.append(f"{slot}={getattr(event, slot)}")
        self._output(f"[debug] t={state.total:.3f} {str(event).upper()} {', '.join(parts)}")

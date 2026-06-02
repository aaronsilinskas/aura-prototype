from __future__ import annotations

try:
    from collections.abc import Callable
except ImportError:
    pass

from engine.engine import GameRule
from engine.events import Event
from engine.state import GameState


class EventLoggerRule(GameRule):
    """Logs every received event along with all its attributes."""

    def __init__(self, output: Callable[[str], None] = lambda s: print(s)) -> None:
        self._output = output

    def handle_event(self, event: Event, state: GameState) -> None:
        parts = []
        cls = type(event)
        while cls is not object:
            for slot in getattr(cls, "__slots__", ()):
                if slot not in ("group", "name"):
                    parts.append(f"{slot}={getattr(event, slot)}")
            cls = cls.__bases__[0] if cls.__bases__ else object
        self._output(f"[debug] t={state.total:.3f} {str(event).upper()} {', '.join(parts)}")


RULE = EventLoggerRule()

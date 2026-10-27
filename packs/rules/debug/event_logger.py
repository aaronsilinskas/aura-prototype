from __future__ import annotations

from engine.engine import GameRule
from engine.events import Event
from engine.state import GameState

_ENABLED_KEY = "event_logging_enabled"


class EventLoggerRule(GameRule):
    """Logs every received event along with all its attributes.

    Logging is off by default. Set ``"event_logging_enabled"`` to ``True`` in a
    scene's ``initial_data`` to log that scene's events.
    """

    __slots__ = ()

    def handle_event(self, event: Event, state: GameState) -> None:
        if not state.get(_ENABLED_KEY, False):
            return
        parts = []
        cls = type(event)
        while cls is not object:
            for slot in getattr(cls, "__slots__", ()):
                if slot not in ("group", "name"):
                    parts.append(f"{slot}={getattr(event, slot)}")
            cls = cls.__bases__[0] if cls.__bases__ else object
        print(f"[debug] t={state.total:.3f} {str(event).upper()} {', '.join(parts)}")


RULE = EventLoggerRule()

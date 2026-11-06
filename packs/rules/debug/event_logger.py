from __future__ import annotations

from engine.engine import GameRule
from engine.events import Event
from engine.state import GameState

try:
    from typing import Final
except ImportError:
    pass  # Not available on CircuitPython/MicroPython

NAMESPACE: Final = "debug"


class EventLoggerRule(GameRule):
    """Logs every received event along with all its attributes.

    Off by default. Set the ``debug`` pack's ``event_logging_enabled`` Setting to
    ``true`` in a scene's pack reference to log that scene's events.
    """

    __slots__ = ()

    def handle_event(self, event: Event, state: GameState) -> None:
        if not state.settings.get(NAMESPACE, "event_logging_enabled"):
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

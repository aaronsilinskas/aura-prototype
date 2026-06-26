from __future__ import annotations

from engine.engine import GameRule
from engine.events import Event
from engine.state import GameState

try:
    from collections.abc import Callable
except ImportError:
    pass


_DEFAULT_ENABLED_KEY = "event_logging_enabled"


class EventLoggerRule(GameRule):
    """Logs every received event along with all its attributes.

    Set the state key (default ``"event_logging_enabled"``) to ``False`` in a
    scene's ``initial_data`` to silence logging for that scene.
    """

    __slots__ = ("_enabled_key", "_output")

    def __init__(
        self,
        output: Callable[[str], None] = lambda s: print(s),
        enabled_key: str = _DEFAULT_ENABLED_KEY,
    ) -> None:
        self._output = output
        self._enabled_key = enabled_key

    def handle_event(self, event: Event, state: GameState) -> None:
        if not state.get(self._enabled_key, False):
            return
        parts = []
        cls = type(event)
        while cls is not object:
            for slot in getattr(cls, "__slots__", ()):
                if slot not in ("group", "name"):
                    parts.append(f"{slot}={getattr(event, slot)}")
            cls = cls.__bases__[0] if cls.__bases__ else object
        self._output(f"[debug] t={state.total:.3f} {str(event).upper()} {', '.join(parts)}")


RULE = EventLoggerRule()

from __future__ import annotations

from engine.events import Event
from engine.state import GameState
from engine.version import Version

TYPE_CHECKING = False

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import TypeVar

    T = TypeVar("T", bound="Event")

__all__ = ["GameRule", "Version"]


class GameRule:
    """Base class for gameplay rules that react to engine events.

    Register per-event-type handlers by calling ``self.on()`` in a subclass
    ``__init__`` (no ``super().__init__()`` required).  Its ``SceneRun`` calls
    ``handle_event`` each tick for every queued event; the dispatch table
    routes to the correct handler by exact event type.
    """

    def on(self, event_type: type[T], handler: Callable[[T, GameState], None]) -> None:
        """Register a handler for a specific event type.

        The handler is called as ``handler(event, state)`` when an event of
        exactly ``event_type`` is dispatched to this rule.  Registering a
        second handler for the same type replaces the first.
        """
        if not hasattr(self, "_event_handlers"):
            self._event_handlers: dict[type, Callable[..., None]] = {}
        self._event_handlers[event_type] = handler

    def handle_event(self, event: Event, state: GameState) -> None:
        handlers = getattr(self, "_event_handlers", None)
        if handlers is not None:
            handler = handlers.get(type(event))
            if handler is not None:
                handler(event, state)

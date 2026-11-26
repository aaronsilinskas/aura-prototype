from __future__ import annotations

from engine.version import Version

TYPE_CHECKING = False

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import TypeVar

    from engine.events import Event
    from engine.state import GameState

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
        exactly ``event_type`` is dispatched to this rule.  A rule has at
        most one handler per event type.

        Raises:
            ValueError: This rule already has a handler for ``event_type``.
        """
        if not hasattr(self, "_event_handlers"):
            self._event_handlers: dict[type, Callable[..., None]] = {}
        if event_type in self._event_handlers:
            raise self._duplicate_handler(event_type)
        self._event_handlers[event_type] = handler

    def handle_event(self, event: Event, state: GameState) -> None:
        handlers = getattr(self, "_event_handlers", None)
        if handlers is not None:
            handler = handlers.get(type(event))
            if handler is not None:
                handler(event, state)

    def _handles(self, event_type: type) -> bool:
        """Return whether this rule has a handler registered for *event_type*."""
        handlers = getattr(self, "_event_handlers", None)
        return handlers is not None and event_type in handlers

    def _duplicate_handler(self, event_type: type) -> ValueError:
        """Return the error for a second handler registered for *event_type*."""
        return ValueError(f"{type(self).__name__} already has a handler for {event_type.__name__}")

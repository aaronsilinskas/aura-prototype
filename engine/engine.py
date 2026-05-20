from __future__ import annotations

from engine.effects.manager import EffectControls
from engine.events import Event
from engine.timer import Timer


class Version:
    """Major and minor version identifier for a game rule."""

    __slots__ = ("major", "minor")

    def __init__(self, major: int, minor: int) -> None:
        self.major = major
        self.minor = minor


class GameRule:
    """Base class for gameplay rules that react to engine events.

    Register per-event-type handlers in ``__init__`` using ``self.on()``.
    The engine calls ``handle_event`` each tick for every queued event;
    the dispatch table routes to the correct handler by exact event type.

    Subclasses must set ``name`` and ``version`` via ``super().__init__``.
    """

    __slots__ = ("_event_handlers", "name", "version")

    def __init__(self, name: str, version: Version) -> None:
        self.name = name
        self.version = version
        self._event_handlers: dict = {}

    def on(self, event_type: type, handler) -> None:
        """Register a handler for a specific event type.

        The handler is called as ``handler(event, state)`` when an event of
        exactly ``event_type`` is dispatched to this rule.  Registering a
        second handler for the same type replaces the first.
        """
        self._event_handlers[event_type] = handler

    def handle_event(self, event: Event, state: GameState) -> None:
        handler = self._event_handlers.get(type(event))
        if handler is not None:
            handler(event, state)


class GameState:
    """Per-tick context passed to every rule handler.

    Provides access to the engine, the current frame timer, and the
    effect controls interface for starting and stopping effects.
    Created fresh each ``update`` tick; do not store references across ticks.
    """

    __slots__ = ("effect_controls", "engine", "timer")

    def __init__(self, engine: GameEngine, timer: Timer, effect_controls: EffectControls) -> None:
        self.engine = engine
        self.timer = timer
        self.effect_controls = effect_controls


class GameEngine:
    """Drives the game loop by dispatching queued events to registered rules.

    Update model:
      - Call ``update(timer)`` once per frame.
      - All queued events are dispatched to all rules in registration order.
      - Rules may queue additional events during dispatch.
    """

    __slots__ = ("_effect_controls", "_queue", "_rules")

    def __init__(self, effect_controls: EffectControls) -> None:
        self._effect_controls = effect_controls
        self._rules: list[GameRule] = []
        self._queue: list[Event] = []

    def update(self, timer: Timer) -> None:
        state = GameState(self, timer, self._effect_controls)
        while self._queue:
            event = self._queue.pop(0)
            for rule in self._rules:
                rule.handle_event(event, state)

    def queue_event(self, event: Event) -> None:
        self._queue.append(event)

    def add_rules(self, *rules: GameRule) -> None:
        self._rules.extend(rules)

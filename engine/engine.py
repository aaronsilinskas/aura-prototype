from __future__ import annotations

from collections.abc import Callable

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
        self._event_handlers: dict[type, Callable[[Event, GameState], None]] = {}

    def on(self, event_type: type, handler: Callable[[Event, GameState], None]) -> None:
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
    """Persistent game context owned by ``GameEngine``.

    Passed by reference to every rule handler on every tick.  Rule-written
    data in ``state.data`` survives across ticks automatically.

    Provides access to time information, the effect controls interface for
    starting and stopping effects, and ``queue_event`` so rules can enqueue
    events without holding a ``GameEngine`` reference.

    Time values are read-only; use ``state.elapsed`` and ``state.total`` to
    read per-tick and cumulative time.
    """

    __slots__ = ("_elapsed", "_total", "_queue", "data", "effect_controls")

    def __init__(
        self,
        effect_controls: EffectControls,
        queue: list[Event],
        data: dict[str, object] | None = None,
    ) -> None:
        self.effect_controls = effect_controls
        self._queue = queue
        self.data: dict[str, object] = data if data is not None else {}
        self._elapsed: float = 0.0
        self._total: float = 0.0

    @property
    def elapsed(self) -> float:
        """Seconds elapsed during the most recent tick."""
        return self._elapsed

    @property
    def total(self) -> float:
        """Cumulative seconds elapsed since the engine started."""
        return self._total

    def queue_event(self, event: Event) -> None:
        """Enqueue an event for processing on the current or next update."""
        self._queue.append(event)

    def _update_time(self, elapsed: float, total: float) -> None:
        """Refresh time values from the engine's timer. Called only by GameEngine."""
        self._elapsed = elapsed
        self._total = total


class GameEngine:
    """Drives the game loop by dispatching queued events to registered rules.

    Update model:
      - Call ``update()`` once per frame.
      - All queued events are dispatched to all rules in registration order.
      - Rules may queue additional events during dispatch.

    An optional ``timer`` argument may be injected at construction time for
    test-time clock control; production code uses the default ``Timer()``.

    An optional ``initial_data`` dict seeds ``state.data`` with starting
    values; the dict is used directly (no copy).
    """

    __slots__ = ("_effect_controls", "_queue", "_rules", "_state", "_timer")

    def __init__(
        self,
        effect_controls: EffectControls,
        timer: Timer | None = None,
        initial_data: dict[str, object] | None = None,
    ) -> None:
        self._effect_controls = effect_controls
        self._timer = timer if timer is not None else Timer()
        self._rules: list[GameRule] = []
        self._queue: list[Event] = []
        self._state = GameState(self._effect_controls, self._queue, initial_data)

    @property
    def state(self) -> GameState:
        """The persistent ``GameState`` shared across all ticks."""
        return self._state

    def update(self) -> None:
        self._timer.update()
        self._state._update_time(self._timer.elapsed, self._timer.total)
        while self._queue:
            event = self._queue.pop(0)
            for rule in self._rules:
                rule.handle_event(event, self._state)

    def queue_event(self, event: Event) -> None:
        self._queue.append(event)

    def add_rules(self, *rules: GameRule) -> None:
        self._rules.extend(rules)

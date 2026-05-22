from __future__ import annotations

try:
    from collections.abc import Callable
except ImportError:
    pass  # No typing support on CircuitPython yet

from engine.effects.manager import EffectControls
from engine.events import Event
from engine.timer import Timer
from engine.version import Version

__all__ = ["GameEngine", "GameRule", "GameState", "SceneControls", "Version"]


class SceneControls:
    """Abstract interface for scene transitions called from within game rules.

    All methods raise ``NotImplementedError`` by default.  ``SceneManager``
    injects itself as the live implementation; standalone callers (e.g. rule
    unit tests) pass the base ``SceneControls()`` instance, which raises on
    any call.

    Transitions are deferred to end-of-tick — the transition is applied after
    ``engine.update(state)`` returns, not immediately inside the rule.
    """

    __slots__ = ()

    def load(self, name: str) -> None:
        """Replace the entire scene stack with the named scene."""
        raise NotImplementedError

    def overlay(self, name: str) -> None:
        """Push the named scene on top, suspending the current scene."""
        raise NotImplementedError

    def pop(self) -> None:
        """Unload the top scene and restore the scene below it."""
        raise NotImplementedError


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
    """Portable game context passed to every rule handler on every tick.

    Create via ``GameEngine.create_state()`` for production use, or directly
    for rule unit tests.  Rule-written data in ``state.data`` survives across
    ticks when the same ``GameState`` instance is passed to each
    ``engine.update(state)`` call.

    Provides access to time information, the effect controls interface for
    starting and stopping effects, and ``queue_event`` so rules can enqueue
    events without holding a ``GameEngine`` reference.

    Time values are read-only; use ``state.elapsed`` and ``state.total`` to
    read per-tick and cumulative time.
    """

    __slots__ = ("_elapsed", "_queue", "_total", "data", "effect_controls", "scene_controls")

    def __init__(
        self,
        effect_controls: EffectControls,
        scene_controls: SceneControls,
        data: dict[str, object] | None = None,
    ) -> None:
        self.effect_controls = effect_controls
        self.scene_controls = scene_controls
        self._queue: list[Event] = []
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

    def clear_queue(self) -> None:
        """Discard all pending events without processing them."""
        self._queue = []

    def _update_time(self, elapsed: float, total: float) -> None:
        """Refresh time values from the engine's timer. Called only by GameEngine."""
        self._elapsed = elapsed
        self._total = total


class GameEngine:
    """Drives the game loop by dispatching queued events to registered rules.

    Update model:
      - Call ``update(state)`` once per frame, passing the active ``GameState``.
      - All queued events are dispatched to all rules in registration order.
      - Rules may queue additional events during dispatch.

    An optional ``timer`` argument may be injected at construction time for
    test-time clock control; production code uses the default ``Timer()``.

    Use ``create_state(scene_controls, initial_data)`` to create a ``GameState``
    pre-wired with this engine's effect controls and the given scene controls.
    """

    __slots__ = ("_effect_controls", "_rules", "_timer")

    def __init__(
        self,
        effect_controls: EffectControls,
        timer: Timer | None = None,
    ) -> None:
        self._effect_controls = effect_controls
        self._timer = timer if timer is not None else Timer()
        self._rules: list[GameRule] = []

    def set_rules(self, rules: list[GameRule]) -> None:
        """Replace the current rule list in full.

        Used by ``SceneManager`` on scene transitions to swap in a new scene's
        rules.  For incremental registration use ``add_rules()`` instead.
        """
        self._rules = list(rules)

    def create_state(
        self,
        scene_controls: SceneControls,
        initial_data: dict[str, object] | None = None,
    ) -> GameState:
        """Create a ``GameState`` pre-wired with this engine's effect controls
        and the given ``scene_controls``.

        The optional ``initial_data`` dict seeds ``state.data`` with starting
        values; the dict is used directly (no copy).
        """
        return GameState(self._effect_controls, scene_controls, initial_data)

    def update(self, state: GameState) -> None:
        """Advance the timer, update state time, and dispatch all queued events."""
        self._timer.update()
        state._update_time(self._timer.elapsed, self._timer.total)
        while state._queue:
            event = state._queue.pop(0)
            for rule in self._rules:
                rule.handle_event(event, state)

    def add_rules(self, *rules: GameRule) -> None:
        self._rules.extend(rules)

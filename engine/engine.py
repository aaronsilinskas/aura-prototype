from __future__ import annotations

try:
    from collections.abc import Callable
    from typing import TypeVar

    T = TypeVar("T", bound="Event")
except ImportError:
    pass  # No typing support on CircuitPython yet

from engine.events import Event
from engine.settings import Settings
from engine.state import EffectControls, GameState, NetworkControls, SceneControls
from engine.timer import Timer
from engine.version import Version

__all__ = ["GameEngine", "GameRule", "Version"]


class GameRule:
    """Base class for gameplay rules that react to engine events.

    Register per-event-type handlers by calling ``self.on()`` in a subclass
    ``__init__`` (no ``super().__init__()`` required).  The engine calls
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


class GameEngine:
    """Drives the game loop by dispatching queued events to registered rules.

    Update model:
      - Advance the timer, then call ``update(state)`` once per frame, passing the
        active ``GameState``.
      - All queued events are dispatched to all rules in registration order.
      - Rules may queue additional events during dispatch.

    ``update`` reads ``timer`` but never advances it: whoever drives the tick
    calls ``timer.update()`` first
    (:meth:`~engine.scene_runtime.SceneRuntime.advance_clock` on device).
    Omitted, the engine gets a ``Timer`` nobody advances, so game time stays
    at zero.

    Use ``create_state(scene_controls, settings)`` to create a ``GameState``
    pre-wired with this engine's effect controls, the given scene controls and
    the scene's Settings.
    """

    __slots__ = ("_capabilities", "_effect_controls", "_network_controls", "_rules", "_timer")

    def __init__(
        self,
        effect_controls: EffectControls,
        timer: Timer | None = None,
        network_controls: NetworkControls | None = None,
        capabilities: frozenset[str] = frozenset(),
    ) -> None:
        self._effect_controls = effect_controls
        self._capabilities = capabilities
        self._network_controls = (
            network_controls if network_controls is not None else NetworkControls()
        )
        self._timer = timer if timer is not None else Timer()
        self._rules: list[GameRule] = []

    @property
    def capabilities(self) -> frozenset[str]:
        """The Capabilities of the device this engine runs on."""
        return self._capabilities

    def set_rules(self, rules: list[GameRule]) -> None:
        """Replace the current rule list in full.

        Used by ``SceneManager`` on scene transitions to swap in a new scene's
        rules.  For incremental registration use ``add_rules()`` instead.
        """
        self._rules = list(rules)

    def create_state(
        self,
        scene_controls: SceneControls,
        settings: Settings | None = None,
    ) -> GameState:
        """Create an empty ``GameState`` pre-wired with this engine's effect
        controls, network controls and Capabilities, and the given ``scene_controls``.

        *settings* is the scene's resolved Settings; the ``get``/``set`` store
        starts empty, for rules to seed their own runtime state.
        """
        return GameState(
            self._effect_controls,
            scene_controls,
            self._network_controls,
            settings=settings,
            capabilities=self._capabilities,
        )

    def update(self, state: GameState) -> None:
        """Add the timer's elapsed time to *state*'s time, then dispatch all queued events."""
        state._advance_time(self._timer.elapsed)
        i = 0
        while i < state.event_count:
            event = state.event_at(i)
            state._begin_dispatch()
            for rule in self._rules:
                rule.handle_event(event, state)
            i += 1
        state.reset_queue()

    def add_rules(self, *rules: GameRule) -> None:
        self._rules.extend(rules)

    @property
    def rules(self) -> list[GameRule]:
        """Return a snapshot of the currently registered rules."""
        return list(self._rules)

from __future__ import annotations

try:
    from collections.abc import Callable
    from typing import TypeVar

    T = TypeVar("T")
except ImportError:
    pass  # No typing support on CircuitPython yet

from engine.events import Event
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


def _check_phase_owners(rules: list[GameRule]) -> None:
    """Raise ``ValueError`` if two rules claim the same ``(machine key, phase)``.

    Duck-typed on ``phase_ownership()`` so the engine stays decoupled from the
    phase primitive: only ``PhaseRule`` exposes it.  ``InPhaseRule``s do not
    own a phase and are skipped, so any number may share a phase.
    """
    owners: dict = {}
    for rule in rules:
        ownership = getattr(rule, "phase_ownership", None)
        if ownership is None:
            continue
        key = ownership()
        if key in owners:
            raise ValueError("Two PhaseRules own the same (machine key, phase): " + repr(key))
        owners[key] = rule


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

    __slots__ = ("_effect_controls", "_network_controls", "_rules", "_timer")

    def __init__(
        self,
        effect_controls: EffectControls,
        timer: Timer | None = None,
        network_controls: NetworkControls | None = None,
    ) -> None:
        self._effect_controls = effect_controls
        self._network_controls = (
            network_controls if network_controls is not None else NetworkControls()
        )
        self._timer = timer if timer is not None else Timer()
        self._rules: list[GameRule] = []

    def set_rules(self, rules: list[GameRule]) -> None:
        """Replace the current rule list in full.

        Used by ``SceneManager`` on scene transitions to swap in a new scene's
        rules.  For incremental registration use ``add_rules()`` instead.

        Raises ``ValueError`` if two ``PhaseRule``s claim the same
        ``(machine key, phase)`` pair, so a duplicate phase owner fails fast at
        scene load rather than silently dropping one rule's ``on_enter`` at
        runtime.
        """
        _check_phase_owners(rules)
        self._rules = list(rules)

    def create_state(
        self,
        scene_controls: SceneControls,
        initial_data: dict[str, object] | None = None,
    ) -> GameState:
        """Create a ``GameState`` pre-wired with this engine's effect controls
        and the given ``scene_controls``.

        The optional ``initial_data`` dict seeds the state's internal store with
        starting values accessible via the typed accessor API; the dict is used
        directly (no copy).
        """
        return GameState(
            self._effect_controls, scene_controls, self._network_controls, initial_data
        )

    def update(self, state: GameState) -> None:
        """Advance the timer, update state time, and dispatch all queued events."""
        self._timer.update()
        state._update_time(self._timer.elapsed, self._timer.total)
        i = 0
        while i < state.event_count:
            event = state.event_at(i)
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

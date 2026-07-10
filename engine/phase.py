"""Reusable phase-machine primitive for scene state machines.

Almost every scene is a state machine: Tag has Ready → Starting → Playing →
Game Over, Red Light Green Light cycles through eight phases, hardware_test
cycles through five modes.  Before this module each scene reinvented the same
four-step boilerplate by hand (do nothing if not my phase, initialise once,
do the per-tick logic, clean up and change state).

This module ships that machinery once:

- :class:`PhaseKey` — an opaque, identity-typed phase token.  The engine ships
  only the *type*; scenes own the named instances.
- :class:`PhaseMachine` — the mutable phase mechanics (current phase, a private
  first-tick entry flag, and ``phase_start``), cached in :class:`GameState`.
- :class:`PhaseSlot` — the one accessor a scene builds per machine, shared by
  every rule that touches it.  See its docstring for the identity contract.
- :class:`PhaseRule` — owns one phase's lifecycle: ``on_enter`` /
  ``on_exit`` hooks plus the scene's normal typed event handlers, all gated to
  fire only while its phase is active.
- :class:`InPhaseRule` — phase-gated handlers without the entry/exit
  lifecycle; any number may share a phase.

The entry flag is consumed atomically by whichever :class:`PhaseRule` first
dispatches while in its phase, so ``on_enter`` fires exactly once per entry
regardless of rule registration order (see :meth:`PhaseMachine.enter`).
"""

from __future__ import annotations

try:
    from collections.abc import Callable
    from typing import TypeVar

    T = TypeVar("T")
except ImportError:
    pass  # No typing support on CircuitPython yet

from engine.engine import GameRule
from engine.events import Event
from engine.state import GameState, StateSlot

__all__ = [
    "InPhaseRule",
    "PhaseKey",
    "PhaseMachine",
    "PhaseRule",
    "PhaseSlot",
]


class PhaseKey:
    """An opaque, identity-typed phase token.

    Compared by identity (no ``__eq__`` override), so two distinct
    ``PhaseKey`` instances never match and a bare string literal never matches
    a ``PhaseKey``.  The engine ships only this type; scenes own the named
    instances they pass to :class:`PhaseMachine` and the phase rules.
    """

    __slots__ = ("_name",)

    def __init__(self, name: str) -> None:
        self._name = name

    def __repr__(self) -> str:
        return "PhaseKey(" + repr(self._name) + ")"


class PhaseMachine:
    """Mutable phase mechanics cached in :class:`GameState`.

    Holds only the current :class:`PhaseKey`, a private first-tick entry flag,
    and ``phase_start``.  It owns no effects and no receipts — :meth:`enter`
    has no side effects beyond the three fields, so it can never leak an
    effect across a transition.  Lifecycle teardown belongs to the owning
    :class:`PhaseRule`'s ``on_exit``.
    """

    __slots__ = ("_just_entered", "phase", "phase_start")

    def __init__(self, initial_phase: PhaseKey) -> None:
        self.phase = initial_phase
        self.phase_start: float = 0.0
        self._just_entered = True

    def enter(self, phase: PhaseKey, now: float) -> None:
        """Atomically set ``phase`` and ``phase_start`` and raise the entry flag.

        Has no other side effects: it never stops effects or clears receipts.
        Because the entry flag persists until consumed, the entering phase's
        ``on_enter`` fires on whichever later dispatch first sees the new
        phase — correctness never depends on rule dispatch order.
        """
        self.phase = phase
        self.phase_start = now
        self._just_entered = True

    def elapsed(self, now: float) -> float:
        """Return the time elapsed since :attr:`phase_start`."""
        return now - self.phase_start

    def take_just_entered(self) -> bool:
        """Return ``True`` on the first dispatch of the current phase, clearing the flag.

        Consumed internally by :class:`PhaseRule` to drive ``on_enter``; this
        is not a public predicate.  Combining the test and the clear into one
        atomic call means the entry signal can be checked exactly once and
        never left half-consumed.
        """
        was_just_entered = self._just_entered
        self._just_entered = False
        return was_just_entered


class PhaseSlot:
    """The one accessor a scene builds per phase machine.

    Owns the machine's ``GameState`` key and initial phase, wrapping a
    :class:`~engine.state.StateSlot` internally (the single
    ``# type: ignore`` cast lives there — see :meth:`StateSlot.__call__`).
    Callable ``(state) -> PhaseMachine``, get-or-create on first use so there
    is no "unestablished key" failure to guard against.

    A scene constructs exactly one ``PhaseSlot`` per machine, e.g.::

        tag_phase = PhaseSlot("tag_phase", PHASE_READY)

    and passes that *same instance* to every :class:`PhaseRule` and
    :class:`InPhaseRule` for that machine, as well as using it directly as the
    scene's own module-level phase reference. Because they all hold the one
    object, they resolve the *same* cached :class:`PhaseMachine` structurally
    — sharing is guaranteed by construction, not by a key string happening to
    match. The load-time guard in ``GameEngine.set_rules`` (via
    ``_check_phase_owners``) is the fail-loud backstop: it raises if two
    *distinct* ``PhaseSlot`` objects ever claim the same key, which would mean
    a rule stopped reusing the scene's shared instance and rebuilt its own.
    """

    __slots__ = ("_slot",)

    def __init__(self, key: str, initial_phase: PhaseKey) -> None:
        self._slot: StateSlot = StateSlot(key, lambda s: PhaseMachine(initial_phase), PhaseMachine)

    @property
    def key(self) -> str:
        """The ``GameState`` key this slot's machine is cached under."""
        return self._slot.key

    def __call__(self, state: GameState) -> PhaseMachine:
        """Return this slot's :class:`PhaseMachine`, creating and caching it on first use."""
        return self._slot(state)


class _PhaseGuardedRule(GameRule):
    """Shared base for phase-gated rules: the ``on`` override and phase guard.

    Overrides :meth:`on` to stash the user handler in a private per-event-type
    map and subscribe a single private dispatcher.  The dispatcher fetches the
    machine through :meth:`_machine`, returns immediately unless the machine is
    in this rule's phase, then defers to subclass behaviour.

    Takes the scene's one :class:`PhaseSlot` for the machine it guards — see
    that class's docstring for the identity contract this relies on.
    """

    def __init__(self, phase: PhaseKey, phase_slot: PhaseSlot) -> None:
        self.phase = phase
        self._phase_slot = phase_slot
        self._phase_handlers: dict[type, Callable[..., None]] = {}

    def on(self, event_type: type[T], handler: Callable[[T, GameState], None]) -> None:
        """Register a phase-gated *handler* for *event_type*.

        Stashes *handler* under *event_type* and subscribes the private phase
        dispatcher in its place, so the inherited :meth:`handle_event` routes
        the event through the phase guard before reaching the user handler.
        """
        self._phase_handlers[event_type] = handler
        super().on(event_type, self._phase_dispatch)

    @property
    def phase_accessor(self) -> PhaseSlot:
        """Duck-typed seam exposing this rule's :class:`PhaseSlot` to the engine.

        ``GameEngine``'s load-time guard reads ``.key`` off the returned
        object to check for two distinct ``PhaseSlot``s claiming one machine
        key, without ``engine/engine.py`` importing this module.
        """
        return self._phase_slot

    def _machine(self, state: GameState) -> PhaseMachine:
        """Return this rule's :class:`PhaseMachine` via its :class:`PhaseSlot`."""
        return self._phase_slot(state)

    def _phase_dispatch(self, event: Event, state: GameState) -> None:
        machine = self._machine(state)
        if machine.phase != self.phase:
            return
        self._before_handler(machine, state)
        handler = self._phase_handlers.get(type(event))
        if handler is not None:
            handler(event, state)

    def _before_handler(self, machine: PhaseMachine, state: GameState) -> None:
        """Hook run after the phase guard passes, before the user handler.

        No-op by default; :class:`PhaseRule` overrides it to drive ``on_enter``.
        """


class PhaseRule(_PhaseGuardedRule):
    """A :class:`GameRule` that owns one phase's lifecycle.

    On the first dispatch after entering its phase, ``on_enter`` runs once and
    then the subscribed handler runs in the same dispatch.  The handler fires
    every tick while the phase is active.  ``on_exit`` runs when a handler
    calls :meth:`transition_to`.  Exactly one ``PhaseRule`` may own a given
    ``(machine key, phase)`` pair; a second is a configuration error caught at
    scene load (see ``GameEngine.set_rules``).
    """

    def transition_to(self, state: GameState, next_phase: PhaseKey) -> None:
        """Run ``on_exit`` then move the machine to *next_phase*.

        Only a handler should call this, and it should return immediately
        after: ``on_enter`` never transitions.  Transitions are free-running
        (no one-per-tick guard); the next phase's ``on_enter`` fires on
        whichever later dispatch first sees it.
        """
        self.on_exit(state)
        self._machine(state).enter(next_phase, state.total)

    def on_enter(self, state: GameState) -> None:
        """Run once on the first dispatch after entering this phase. No-op by default."""

    def on_exit(self, state: GameState) -> None:
        """Run when :meth:`transition_to` leaves this phase. No-op by default."""

    def phase_ownership(self) -> tuple[str, PhaseKey]:
        """Return the ``(machine key, phase)`` pair this rule claims ownership of.

        Used by ``GameEngine.set_rules`` to fail fast when two ``PhaseRule``s
        claim the same pair.
        """
        return (self._phase_slot.key, self.phase)

    def _before_handler(self, machine: PhaseMachine, state: GameState) -> None:
        if machine.take_just_entered():
            self.on_enter(state)


class InPhaseRule(_PhaseGuardedRule):
    """A :class:`GameRule` whose handlers fire only while its phase is active.

    Shares the phase-gated ``on`` override and forwarding with
    :class:`PhaseRule` but has no entry/exit lifecycle: it never consumes the
    entry flag and has no ``on_enter`` / ``on_exit`` / ``transition_to``.  Any
    number of ``InPhaseRule``s may share a phase, and an ``InPhaseRule`` may
    share a phase with that phase's owning :class:`PhaseRule`.
    """

"""Reusable phase-machine primitive for scene state machines.

Almost every scene is a state machine: Tag has Ready → Starting → Playing →
Game Over, Red Light Green Light cycles through eight phases, hardware_test
cycles through six modes.  Before this module each scene reinvented the same
four-step boilerplate by hand (do nothing if not my phase, initialise once,
do the per-tick logic, clean up and change state).

This module ships that machinery once:

- :class:`PhaseKey` — an opaque, identity-typed phase token.  The engine ships
  only the *type*; scenes own the named instances.
- :class:`PhaseMachine` — the mutable phase mechanics (current phase, a private
  pending-entry flag, and ``phase_start``), cached in :class:`GameState`.
- :class:`PhaseSlot` — the one accessor a scene builds per machine, shared by
  every rule that touches it.  See its docstring for the identity contract.
- :class:`PhaseRule` — owns one phase's lifecycle: ``on_enter`` /
  ``on_exit`` hooks plus the scene's normal typed event handlers, all gated to
  fire only while its phase is active.
- :class:`InPhaseRule` — phase-gated handlers without the entry/exit
  lifecycle; any number may share a phase.

A phase starts in the tick it is entered, whatever order the scene's rules
run in: :meth:`PhaseRule.transition_to` runs the entering phase's ``on_enter``
itself, finding its owner through the :class:`PhaseSlot`.  The initial phase
has no transition, so its ``on_enter`` runs on its owner's first dispatch.
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
        return f"PhaseKey({self._name!r})"


class PhaseMachine:
    """Mutable phase mechanics cached in :class:`GameState`.

    Holds only the current :class:`PhaseKey`, ``phase_start``, and private
    flags marking an ``on_enter`` as pending or running.  It owns no effects
    and no receipts — :meth:`enter` has no side effects beyond those fields,
    so it can never leak an effect across a transition.  Lifecycle teardown belongs to the owning
    :class:`PhaseRule`'s ``on_exit``.
    """

    __slots__ = ("_entering", "_just_entered", "phase", "phase_start")

    def __init__(self, initial_phase: PhaseKey) -> None:
        self.phase = initial_phase
        self.phase_start: float = 0.0
        self._just_entered = True
        self._entering = False

    def enter(self, phase: PhaseKey, now: float) -> None:
        """Atomically set ``phase`` and ``phase_start`` and mark ``on_enter`` pending.

        Has no other side effects: it never stops effects or clears receipts,
        and it does not run ``on_enter`` itself — :meth:`PhaseRule.transition_to`
        does, straight after.
        """
        self.phase = phase
        self.phase_start = now
        self._just_entered = True

    def elapsed(self, now: float) -> float:
        """Return the time elapsed since :attr:`phase_start`."""
        return now - self.phase_start

    def take_just_entered(self) -> bool:
        """Return ``True`` if the current phase's ``on_enter`` is pending, clearing the flag.

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
    match.  Two slots sharing one key are unsupported.

    The slot also knows which :class:`PhaseRule` owns each of its phases (see
    :meth:`owner_of`).
    """

    __slots__ = ("_owners", "_slot")

    def __init__(self, key: str, initial_phase: PhaseKey) -> None:
        self._slot: StateSlot = StateSlot(key, lambda s: PhaseMachine(initial_phase), PhaseMachine)
        self._owners: dict[PhaseKey, PhaseRule] = {}

    @property
    def key(self) -> str:
        """The ``GameState`` key this slot's machine is cached under."""
        return self._slot.key

    def __call__(self, state: GameState) -> PhaseMachine:
        """Return this slot's :class:`PhaseMachine`, creating and caching it on first use."""
        return self._slot(state)

    def owner_of(self, phase: PhaseKey) -> PhaseRule | None:
        """Return the :class:`PhaseRule` owning *phase*, or ``None`` if none has been built."""
        return self._owners.get(phase)

    def _register_owner(self, rule: PhaseRule) -> None:
        if rule.phase in self._owners:
            raise ValueError(f"Phase {rule.phase!r} of {self.key!r} already has an owner")
        self._owners[rule.phase] = rule


class _PhaseGuardedRule(GameRule):
    """Shared base for phase-gated rules: the ``on`` override and phase guard.

    Overrides :meth:`on` to stash the user handler in a private per-event-type
    map and subscribe a single private dispatcher.  The dispatcher fetches the
    machine through :meth:`_machine`, returns immediately unless the machine is
    in this rule's phase, then defers to subclass behaviour.

    Takes the scene's one :class:`PhaseSlot` for the machine it guards, through
    which it reaches the shared :class:`PhaseMachine`.
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

    ``on_enter`` runs once per entry: inside the :meth:`transition_to` that
    enters the phase or, for the scene's initial phase, on this rule's first
    dispatch, just before its handler.  The handler fires every tick while the
    phase is active.  ``on_exit`` runs when a handler calls
    :meth:`transition_to`.  Exactly one ``PhaseRule`` may own a given
    phase of a :class:`PhaseSlot`: each registers itself with its slot when
    constructed, and constructing a second owner raises ``ValueError``.
    """

    def __init__(self, phase: PhaseKey, phase_slot: PhaseSlot) -> None:
        super().__init__(phase, phase_slot)
        phase_slot._register_owner(self)

    def transition_to(self, state: GameState, next_phase: PhaseKey) -> None:
        """Run ``on_exit``, move the machine to *next_phase*, then run its ``on_enter``.

        The entering phase's owner is found through the :class:`PhaseSlot`.
        Only a handler should call this, and it should return immediately
        after.  Transitions are free-running (no one-per-tick guard).

        Raises ``RuntimeError`` when called while an ``on_enter`` is running,
        and ``ValueError`` when no :class:`PhaseRule` owns *next_phase*; both
        are checked before ``on_exit`` runs.
        """
        machine = self._machine(state)
        if machine._entering:
            raise RuntimeError(f"transition_to({next_phase!r}) called from on_enter")
        owner = self._phase_slot.owner_of(next_phase)
        if owner is None:
            raise ValueError(f"Phase {next_phase!r} of {self._phase_slot.key!r} has no owner")
        self.on_exit(state)
        machine.enter(next_phase, state.total)
        owner._start(machine, state)

    def on_enter(self, state: GameState) -> None:
        """Run once each time this phase is entered. No-op by default; must not transition."""

    def on_exit(self, state: GameState) -> None:
        """Run when :meth:`transition_to` leaves this phase. No-op by default."""

    def _before_handler(self, machine: PhaseMachine, state: GameState) -> None:
        self._start(machine, state)

    def _start(self, machine: PhaseMachine, state: GameState) -> None:
        if not machine.take_just_entered():
            return
        machine._entering = True
        try:
            self.on_enter(state)
        finally:
            machine._entering = False


class InPhaseRule(_PhaseGuardedRule):
    """A :class:`GameRule` whose handlers fire only while its phase is active.

    Shares the phase-gated ``on`` override and forwarding with
    :class:`PhaseRule` but has no entry/exit lifecycle: it never runs the
    pending ``on_enter`` and has no ``on_enter`` / ``on_exit`` / ``transition_to``.  Any
    number of ``InPhaseRule``s may share a phase, and an ``InPhaseRule`` may
    share a phase with that phase's owning :class:`PhaseRule`.
    """

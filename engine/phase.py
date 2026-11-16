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
  pending-entry flag, ``phase_start`` and the phase's pending end), cached in
  :class:`GameState`.
- :class:`PhaseSlot` — the one accessor a scene builds per machine, shared by
  every rule that touches it.  See its docstring for the identity contract.
- :class:`PhaseRule` — owns one phase's lifecycle: ``on_enter`` /
  ``on_exit`` hooks plus the scene's normal typed event handlers, all gated to
  fire only while its phase is active.
- :class:`InPhaseRule` — phase-gated handlers without the entry/exit
  lifecycle; any number may share a phase.

Both kinds of phase rule read how long their own phase has run with
``phase_elapsed``, without reaching through the :class:`PhaseSlot`.

A phase starts in the tick it is entered, whatever order the scene's rules
run in: :meth:`PhaseRule.transition_to` runs the entering phase's ``on_enter``
itself, finding its owner through the :class:`PhaseSlot`.  The initial phase
has no transition, so its ``on_enter`` runs on the first event any phase rule
on the slot hears, before that rule's handler.

A newly entered phase's handlers, on both :class:`PhaseRule` and
:class:`InPhaseRule`, first hear the event *after* the one that entered it,
again whatever the rule order.  The engine counts every event it dispatches
(:attr:`GameState.dispatch_count`) and the machine records the count at
entry, so this holds even for the reused per-frame ``Sensors`` event.

A phase ends when its owning :class:`PhaseRule` calls
:meth:`~PhaseRule.transition_to` from a handler, or when the end it declared
in ``on_enter`` fires: after a duration, when an effect receipt stops, or
when a condition on game state holds, each naming the next phase.  The
machine holds at most one such pending end and drops it on every
transition, so a phase's end belongs to that one entry.  The end is checked
once per tick on the ``Sensors`` event, before the owning rule's own
``Sensors`` handler, which is skipped on the tick it fires.  It is measured
in game time, so like the phase itself it pauses under an Overlay.
"""

from __future__ import annotations

try:
    from collections.abc import Callable
    from typing import TypeVar

    T = TypeVar("T", bound="Event")
except ImportError:
    pass  # No typing support on CircuitPython yet

from engine.engine import GameRule
from engine.events import Event
from engine.input import InputEvents
from engine.state import EffectReceipt, GameState, StateSlot

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

    Holds only the current :class:`PhaseKey`, ``phase_start``, the
    :attr:`GameState.dispatch_count` the phase was entered on, private
    flags marking an ``on_enter`` as pending or running, and at most one
    pending end, dropped on transition; it never stops an effect.  :meth:`enter`
    has no side effects beyond those fields, so it can never leak an effect
    across a transition.  Lifecycle teardown belongs to the owning
    :class:`PhaseRule`'s ``on_exit``.
    """

    __slots__ = (
        "_enter_pending",
        "_entering",
        "_entry_dispatch",
        "_pending_end",
        "phase",
        "phase_start",
    )

    def __init__(self, initial_phase: PhaseKey) -> None:
        self.phase = initial_phase
        self.phase_start: float = 0.0
        # No event is dispatched as 0, so the initial phase hears the first one.
        self._entry_dispatch = 0
        self._enter_pending = True
        self._entering = False
        # The current phase's declared end: its condition and next phase.
        self._pending_end: tuple[Callable[[GameState], bool], PhaseKey] | None = None

    def enter(self, phase: PhaseKey, now: float, dispatch: int) -> None:
        """Atomically move to *phase* at *now* on *dispatch* and mark ``on_enter`` pending.

        *dispatch* is the :attr:`GameState.dispatch_count` of the event being
        dispatched at entry; the phase's handlers skip that event.

        Drops any pending end, so every transition cancels the leaving
        phase's declared end.  Has no other side effects: it never stops
        effects or clears receipts, and it does not run ``on_enter`` itself —
        :meth:`PhaseRule.transition_to` does, straight after.
        """
        self.phase = phase
        self.phase_start = now
        self._entry_dispatch = dispatch
        self._enter_pending = True
        self._pending_end = None

    def elapsed(self, now: float) -> float:
        """Return the time elapsed since :attr:`phase_start`."""
        return now - self.phase_start

    def take_enter_pending(self) -> bool:
        """Return ``True`` if the current phase's ``on_enter`` is pending, clearing the flag.

        Consumed internally by :class:`PhaseRule` to drive ``on_enter``; this
        is not a public predicate.  Combining the test and the clear into one
        atomic call means the entry signal can be checked exactly once and
        never left half-consumed.
        """
        was_pending = self._enter_pending
        self._enter_pending = False
        return was_pending


class PhaseSlot:
    """The one accessor a scene builds per phase machine.

    Owns the machine's ``GameState`` key and initial phase, wrapping a
    :class:`~engine.state.StateSlot` internally.
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
        self._slot = StateSlot(key, lambda s: PhaseMachine(initial_phase), PhaseMachine)
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
    machine through :meth:`_machine` and first runs the initial phase owner's
    ``on_enter`` if it is still pending, whatever this rule's phase.  It then
    returns unless the machine is in this rule's phase and the event is not
    the one dispatched when that phase was entered, and otherwise calls the
    user handler.

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

    def phase_elapsed(self, state: GameState) -> float:
        """Return how long this rule's phase has run, in game time.

        Read it from this rule's handlers or ``on_enter``, while its phase is
        active; it restarts from zero each time the phase is entered.  Game
        time does not advance while the scene is covered by an Overlay.
        """
        return self._machine(state).elapsed(state.total)

    def _machine(self, state: GameState) -> PhaseMachine:
        """Return this rule's :class:`PhaseMachine` via its :class:`PhaseSlot`."""
        return self._phase_slot(state)

    def _end_fired(self, event: Event, machine: PhaseMachine, state: GameState) -> bool:
        """Return ``True`` if this rule ended its phase on *event*; only a PhaseRule can."""
        return False

    def _phase_dispatch(self, event: Event, state: GameState) -> None:
        machine = self._machine(state)
        if machine._enter_pending:
            # Only the initial phase is still pending here: transition_to runs
            # every entered phase's on_enter itself.
            owner = self._phase_slot.owner_of(machine.phase)
            if owner is not None:
                owner._run_pending_enter(machine, state)
        if machine.phase != self.phase or machine._entry_dispatch == state.dispatch_count:
            return
        if self._end_fired(event, machine, state):
            return
        handler = self._phase_handlers.get(type(event))
        if handler is not None:
            handler(event, state)


class PhaseRule(_PhaseGuardedRule):
    """A :class:`GameRule` that owns one phase's lifecycle.

    ``on_enter`` runs once per entry: inside the :meth:`transition_to` that
    enters the phase or, for the scene's initial phase, on the first event any
    phase rule on its slot hears, before that rule's handler.  The handlers
    fire for every event while the phase is active, starting with the event
    after the one that entered it.  ``on_exit`` runs when the phase is left,
    by a handler calling :meth:`transition_to` or by the end ``on_enter``
    declared (:meth:`end_when` and its named forms).  Exactly one
    ``PhaseRule`` may own a given phase of a :class:`PhaseSlot`: each
    registers itself with its slot when constructed, and constructing a
    second owner raises ``ValueError``.
    """

    def __init__(self, phase: PhaseKey, phase_slot: PhaseSlot) -> None:
        super().__init__(phase, phase_slot)
        phase_slot._register_owner(self)
        # A declared end is checked on Sensors whether or not a handler is registered for it.
        GameRule.on(self, InputEvents.Sensors, self._phase_dispatch)

    def transition_to(self, state: GameState, next_phase: PhaseKey) -> None:
        """Run ``on_exit``, move the machine to *next_phase*, then run its ``on_enter``.

        The entering phase's owner is found through the :class:`PhaseSlot`.
        Only a handler should call this, and it should return immediately
        after.  Transitions are free-running (no one-per-tick guard).

        Both misuses below are caught before ``on_exit`` runs.

        Raises:
            RuntimeError: if called while an ``on_enter`` is running.
            ValueError: if no :class:`PhaseRule` owns *next_phase*.
        """
        machine = self._machine(state)
        if machine._entering:
            raise RuntimeError(f"transition_to({next_phase!r}) called from on_enter")
        owner = self._phase_slot.owner_of(next_phase)
        if owner is None:
            raise ValueError(f"Phase {next_phase!r} of {self._phase_slot.key!r} has no owner")
        self.on_exit(state)
        machine.enter(next_phase, state.total, state.dispatch_count)
        owner._run_pending_enter(machine, state)

    def end_when(
        self, state: GameState, condition: Callable[[GameState], bool], next_phase: PhaseKey
    ) -> None:
        """Declare that this phase ends, moving to *next_phase*, once *condition* holds.

        Call it from ``on_enter``.  *condition* receives the game state only
        and is checked once per tick on the ``Sensors`` event, from the one
        after entry, before this rule's own ``Sensors`` handler, which is
        skipped on the tick the end fires.  Any transition cancels it,
        including this rule's own :meth:`transition_to`.

        Raises:
            RuntimeError: if called anywhere but this rule's ``on_enter``, or
                if this phase entry already declared an end.
        """
        machine = self._machine(state)
        if not machine._entering or machine.phase is not self.phase:
            raise RuntimeError(f"End of {self.phase!r} declared outside its on_enter")
        if machine._pending_end is not None:
            raise RuntimeError(f"End of {self.phase!r} already declared for this entry")
        machine._pending_end = (condition, next_phase)

    def end_after(self, state: GameState, seconds: float, next_phase: PhaseKey) -> None:
        """Declare that this phase ends, moving to *next_phase*, once it has run *seconds*.

        A named form of :meth:`end_when`, with its rules; *seconds* is read
        once, at the call.  Game time stops under an Overlay, so this end
        pauses with it.
        """
        self.end_when(state, lambda s: self.phase_elapsed(s) >= seconds, next_phase)

    def end_when_stopped(
        self, state: GameState, receipt: EffectReceipt, next_phase: PhaseKey
    ) -> None:
        """Declare that this phase ends, moving to *next_phase*, once *receipt*'s effect stops.

        A named form of :meth:`end_when`, with its rules.  Ending the phase
        never stops the effect, and a transition that cancels this end
        leaves the effect running.
        """
        self.end_when(state, lambda s: receipt.is_stopped(), next_phase)

    def on_enter(self, state: GameState) -> None:
        """Run once each time this phase is entered. No-op by default; must not transition."""

    def on_exit(self, state: GameState) -> None:
        """Run when :meth:`transition_to` leaves this phase. No-op by default."""

    def _end_fired(self, event: Event, machine: PhaseMachine, state: GameState) -> bool:
        pending_end = machine._pending_end
        if pending_end is None or type(event) is not InputEvents.Sensors:
            return False
        condition, next_phase = pending_end
        if not condition(state):
            return False
        self.transition_to(state, next_phase)
        return True

    def _run_pending_enter(self, machine: PhaseMachine, state: GameState) -> None:
        if not machine.take_enter_pending():
            return
        machine._entering = True
        try:
            self.on_enter(state)
        finally:
            machine._entering = False


class InPhaseRule(_PhaseGuardedRule):
    """A :class:`GameRule` whose handlers fire only while its phase is active.

    Shares the phase-gated ``on`` override and forwarding with
    :class:`PhaseRule` but has no entry/exit lifecycle: it has no
    ``on_enter`` / ``on_exit`` / ``transition_to``, though it may trigger the
    initial phase owner's pending ``on_enter``.  Like a :class:`PhaseRule`,
    its handlers start with the event after the one that entered its phase.
    Any number of ``InPhaseRule``s may share a phase, and an ``InPhaseRule``
    may share a phase with that phase's owning :class:`PhaseRule`.
    """

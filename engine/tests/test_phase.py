"""Behaviour tests for the phase-machine engine primitive.

Lifecycle behaviour (``on_enter`` / handler / ``on_exit``) is exercised
through a real ``SceneRun.tick`` + ``SpyEffectControls`` seam using
throwaway rule subclasses that emit a uniquely-named effect at each lifecycle
point.  Tests assert on those observable effects only — never on the machine's
private entry flag.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from engine.engine import GameRule
from engine.events import Event, EventGroup
from engine.input import ButtonData, InputEvents
from engine.phase import (
    InPhaseRule,
    PhaseKey,
    PhaseMachine,
    PhaseRule,
    PhaseSlot,
)
from engine.state import EffectReceipt, GameState, SceneControls, SceneRun, Scope
from engine.tests.helpers import SpyEffectControls

_GROUP = EventGroup("phase_test")


class _TickEvent(Event):
    __slots__ = ()

    def __init__(self) -> None:
        super().__init__(_GROUP, "tick")


_PHASE_A = PhaseKey("a")
_PHASE_B = PhaseKey("b")
_MACHINE_KEY = "test_machine"


class _LifecycleRule(PhaseRule):
    """PhaseRule that emits ``enter:``/``tick:``/``exit:`` effects, optionally transitioning."""

    def __init__(
        self,
        phase: PhaseKey,
        label: str,
        phase_slot: PhaseSlot,
        transitions_to: PhaseKey | None = None,
    ) -> None:
        super().__init__(phase, phase_slot)
        self._label = label
        self._transitions_to = transitions_to
        self.on(_TickEvent, self._tick)

    def on_enter(self, state: GameState) -> None:
        state.effect_controls.add_effect(Scope.PERSONAL, "enter:" + self._label, {})

    def on_exit(self, state: GameState) -> None:
        state.effect_controls.add_effect(Scope.PERSONAL, "exit:" + self._label, {})

    def _tick(self, event: _TickEvent, state: GameState) -> None:
        state.effect_controls.add_effect(Scope.PERSONAL, "tick:" + self._label, {})
        if self._transitions_to is not None:
            self.transition_to(state, self._transitions_to)
            self._transitions_to = None


class _DeafOwner(PhaseRule):
    """PhaseRule that emits ``enter:`` but subscribes to no event, so is never dispatched."""

    def __init__(self, phase: PhaseKey, label: str, phase_slot: PhaseSlot) -> None:
        super().__init__(phase, phase_slot)
        self._label = label

    def on_enter(self, state: GameState) -> None:
        state.effect_controls.add_effect(Scope.PERSONAL, "enter:" + self._label, {})


class _TransitionsOnEnterRule(PhaseRule):
    """PhaseRule whose ``on_enter`` (wrongly) transitions straight to another phase."""

    def __init__(self, phase: PhaseKey, phase_slot: PhaseSlot, transitions_to: PhaseKey) -> None:
        super().__init__(phase, phase_slot)
        self._transitions_to = transitions_to
        self.on(_TickEvent, self._tick)

    def on_enter(self, state: GameState) -> None:
        self.transition_to(state, self._transitions_to)

    def _tick(self, event: _TickEvent, state: GameState) -> None:
        pass


class _QueuesOneTickRule(GameRule):
    """Plain rule that queues one more ``_TickEvent`` the first time it hears one."""

    def __init__(self) -> None:
        self._queued = False
        self.on(_TickEvent, self._tick)

    def _tick(self, event: _TickEvent, state: GameState) -> None:
        if not self._queued:
            self._queued = True
            state.queue_event(_TickEvent())


class _InPhaseEmitter(InPhaseRule):
    """InPhaseRule that emits an ``in:`` effect each tick its phase is active."""

    def __init__(
        self,
        phase: PhaseKey,
        label: str,
        phase_slot: PhaseSlot,
    ) -> None:
        super().__init__(phase, phase_slot)
        self._label = label
        self.on(_TickEvent, self._tick)

    def _tick(self, event: _TickEvent, state: GameState) -> None:
        state.effect_controls.add_effect(Scope.PERSONAL, "in:" + self._label, {})


class _ElapsedRecordingOwner(PhaseRule):
    """PhaseRule recording its phase elapsed each tick, leaving for *next_phase* at 1 s."""

    def __init__(self, phase: PhaseKey, phase_slot: PhaseSlot, next_phase: PhaseKey) -> None:
        super().__init__(phase, phase_slot)
        self._next_phase = next_phase
        self.readings: list[float] = []
        self.on(_TickEvent, self._tick)

    def _tick(self, event: _TickEvent, state: GameState) -> None:
        elapsed = self.phase_elapsed(state)
        self.readings.append(elapsed)
        if elapsed >= 1.0:
            self.transition_to(state, self._next_phase)


class _ElapsedRecordingBystander(InPhaseRule):
    """InPhaseRule recording its phase elapsed each tick its phase is active."""

    def __init__(self, phase: PhaseKey, phase_slot: PhaseSlot) -> None:
        super().__init__(phase, phase_slot)
        self.readings: list[float] = []
        self.on(_TickEvent, self._tick)

    def _tick(self, event: _TickEvent, state: GameState) -> None:
        self.readings.append(self.phase_elapsed(state))


def _run_timed(rules: list, ticks: int, step: float) -> None:
    """Run *rules* through *ticks* SceneRun ticks of *step* seconds, one event each."""
    state = GameState(SpyEffectControls(), SceneControls())
    run = SceneRun(state, rules)
    for _ in range(ticks):
        state.queue_event(_TickEvent())
        run.tick(step)


def _run(rules: list, ticks: int, events_per_tick: int = 1) -> list[str]:
    """Run *rules* through *ticks* SceneRun ticks; return emitted effect names in order."""
    spy = SpyEffectControls()
    state = GameState(spy, SceneControls())
    run = SceneRun(state, rules)
    for _ in range(ticks):
        for _ in range(events_per_tick):
            state.queue_event(_TickEvent())
        run.tick(0.0)
    return [name for _, name, _ in spy.add_effect_calls]


def _rule_machine(rule: PhaseRule | InPhaseRule, state: GameState) -> PhaseMachine:
    """Dedicated helper: expose a rule's internal machine for seam-level identity tests."""
    return rule._machine(state)


def test_phase_key_never_equals_a_bare_string() -> None:
    machine = PhaseMachine(_PHASE_A)

    assert (machine.phase == "a") is False
    assert machine.phase != "a"


def test_distinct_phase_keys_with_the_same_name_are_not_equal() -> None:
    assert PhaseKey("ready") != PhaseKey("ready")


def test_enter_sets_phase_and_phase_start_and_raises_the_entry_flag() -> None:
    machine = PhaseMachine(_PHASE_A)
    machine.take_enter_pending()  # consume the initial flag

    machine.enter(_PHASE_B, now=4.0, dispatch=1)

    assert machine.phase is _PHASE_B
    assert machine.phase_start == 4.0
    assert machine.take_enter_pending() is True


def test_elapsed_reports_the_gap_since_entry() -> None:
    machine = PhaseMachine(_PHASE_A)
    machine.enter(_PHASE_B, now=10.0, dispatch=1)

    assert machine.elapsed(now=13.5) == pytest.approx(3.5)


def test_take_enter_pending_returns_true_once_then_false() -> None:
    machine = PhaseMachine(_PHASE_A)

    assert machine.take_enter_pending() is True
    assert machine.take_enter_pending() is False


def test_phase_slot_creates_a_machine_at_the_initial_phase_on_first_call() -> None:
    slot = PhaseSlot("some_machine", _PHASE_A)
    state = GameState(SpyEffectControls(), SceneControls())

    machine = slot(state)

    assert machine.phase is _PHASE_A


def test_phase_slot_returns_the_same_cached_machine_on_repeated_calls() -> None:
    slot = PhaseSlot("some_machine", _PHASE_A)
    state = GameState(SpyEffectControls(), SceneControls())

    first = slot(state)
    second = slot(state)

    assert first is second


def test_phase_slot_exposes_its_key() -> None:
    slot = PhaseSlot("some_machine", _PHASE_A)

    assert slot.key == "some_machine"


def test_the_initial_phases_on_enter_runs_once_on_the_first_dispatch() -> None:
    rule = _LifecycleRule(_PHASE_A, "owner", PhaseSlot(_MACHINE_KEY, _PHASE_A))

    names = _run([rule], ticks=3)

    assert names == ["enter:owner", "tick:owner", "tick:owner", "tick:owner"]


def test_on_exit_fires_on_transition_and_the_next_phase_enters() -> None:
    slot = PhaseSlot(_MACHINE_KEY, _PHASE_A)
    leaving = _LifecycleRule(_PHASE_A, "a", phase_slot=slot, transitions_to=_PHASE_B)
    arriving = _LifecycleRule(_PHASE_B, "b", phase_slot=slot)

    names = _run([leaving, arriving], ticks=2)

    # tick1: A enters and ticks, then transitions out: A exits and B enters in
    # the same call. tick2: only B is active and ticks.
    assert names == ["enter:a", "tick:a", "exit:a", "enter:b", "tick:b"]


def test_handler_does_not_fire_after_its_phase_is_left() -> None:
    slot = PhaseSlot(_MACHINE_KEY, _PHASE_A)
    leaving = _LifecycleRule(_PHASE_A, "a", phase_slot=slot, transitions_to=_PHASE_B)
    arriving = _LifecycleRule(_PHASE_B, "b", phase_slot=slot)

    names = _run([leaving, arriving], ticks=4)

    assert "tick:a" in names
    assert names.count("tick:a") == 1  # only the entry tick, never after leaving A


def test_an_owner_registered_before_the_transitioning_rule_enters_during_the_transition() -> None:
    slot = PhaseSlot(_MACHINE_KEY, _PHASE_A)
    arriving = _LifecycleRule(_PHASE_B, "b", phase_slot=slot)
    leaving = _LifecycleRule(_PHASE_A, "a", phase_slot=slot, transitions_to=_PHASE_B)

    names = _run([arriving, leaving], ticks=1)

    assert names[-2:] == ["exit:a", "enter:b"]


@pytest.mark.parametrize("owner_dispatches_first", [True, False])
def test_an_entered_phases_handler_does_not_see_the_event_that_entered_it(
    owner_dispatches_first: bool,
) -> None:
    slot = PhaseSlot(_MACHINE_KEY, _PHASE_A)
    leaving = _LifecycleRule(_PHASE_A, "a", phase_slot=slot, transitions_to=_PHASE_B)
    arriving = _LifecycleRule(_PHASE_B, "b", phase_slot=slot)
    rules = [arriving, leaving] if owner_dispatches_first else [leaving, arriving]

    names = _run(rules, ticks=1)

    assert names == ["enter:a", "tick:a", "exit:a", "enter:b"]


@pytest.mark.parametrize("bystander_dispatches_first", [True, False])
def test_an_entered_phases_in_phase_rule_does_not_see_the_event_that_entered_it(
    bystander_dispatches_first: bool,
) -> None:
    slot = PhaseSlot(_MACHINE_KEY, _PHASE_A)
    bystander = _InPhaseEmitter(_PHASE_B, "bystander", phase_slot=slot)
    leaving = _LifecycleRule(_PHASE_A, "a", phase_slot=slot, transitions_to=_PHASE_B)
    # Built only to register B's owner with the slot; transition_to needs one.
    _owner = _LifecycleRule(_PHASE_B, "b", phase_slot=slot)
    rules = [bystander, leaving] if bystander_dispatches_first else [leaving, bystander]

    names = _run(rules, ticks=1)

    assert "enter:b" in names
    assert "in:bystander" not in names


def test_an_entered_phases_handlers_see_the_next_event_queued_in_the_same_tick() -> None:
    slot = PhaseSlot(_MACHINE_KEY, _PHASE_A)
    leaving = _LifecycleRule(_PHASE_A, "a", phase_slot=slot, transitions_to=_PHASE_B)
    arriving = _LifecycleRule(_PHASE_B, "b", phase_slot=slot)
    bystander = _InPhaseEmitter(_PHASE_B, "bystander", phase_slot=slot)

    names = _run([leaving, arriving, bystander], ticks=1, events_per_tick=2)

    assert names == ["enter:a", "tick:a", "exit:a", "enter:b", "tick:b", "in:bystander"]


def test_an_entered_phases_handlers_see_an_event_queued_during_the_entering_dispatch() -> None:
    slot = PhaseSlot(_MACHINE_KEY, _PHASE_A)
    queuer = _QueuesOneTickRule()
    leaving = _LifecycleRule(_PHASE_A, "a", phase_slot=slot, transitions_to=_PHASE_B)
    arriving = _LifecycleRule(_PHASE_B, "b", phase_slot=slot)

    names = _run([queuer, leaving, arriving], ticks=1)

    assert names == ["enter:a", "tick:a", "exit:a", "enter:b", "tick:b"]


def test_transitioning_to_a_phase_no_phase_rule_owns_raises_naming_the_phase() -> None:
    slot = PhaseSlot(_MACHINE_KEY, _PHASE_A)
    leaving = _LifecycleRule(_PHASE_A, "a", phase_slot=slot, transitions_to=_PHASE_B)

    with pytest.raises(ValueError, match="PhaseKey\\('b'\\)"):
        _run([leaving], ticks=1)


def test_transitioning_from_the_initial_phases_on_enter_raises() -> None:
    slot = PhaseSlot(_MACHINE_KEY, _PHASE_A)
    rule = _TransitionsOnEnterRule(_PHASE_A, slot, transitions_to=_PHASE_B)
    _LifecycleRule(_PHASE_B, "b", phase_slot=slot)

    with pytest.raises(RuntimeError):
        _run([rule], ticks=1)


def test_transitioning_from_an_entered_phases_on_enter_raises() -> None:
    slot = PhaseSlot(_MACHINE_KEY, _PHASE_A)
    leaving = _LifecycleRule(_PHASE_A, "a", phase_slot=slot, transitions_to=_PHASE_B)
    _TransitionsOnEnterRule(_PHASE_B, slot, transitions_to=_PHASE_A)

    with pytest.raises(RuntimeError):
        _run([leaving], ticks=1)


@pytest.mark.parametrize("owner_dispatches_first", [True, False])
def test_on_enter_fires_exactly_once_regardless_of_dispatch_order(
    owner_dispatches_first: bool,
) -> None:
    slot = PhaseSlot(_MACHINE_KEY, _PHASE_A)
    leaving = _LifecycleRule(_PHASE_A, "a", phase_slot=slot, transitions_to=_PHASE_B)
    arriving = _LifecycleRule(_PHASE_B, "b", phase_slot=slot)
    rules = [arriving, leaving] if owner_dispatches_first else [leaving, arriving]

    names = _run(rules, ticks=4)

    assert names.count("enter:b") == 1


def test_in_phase_rule_handler_fires_only_while_its_phase_is_active() -> None:
    # bystander registered first so it dispatches before the transition each
    # tick: it must not catch the same-tick switch into B on the transition tick.
    slot = PhaseSlot(_MACHINE_KEY, _PHASE_A)
    bystander = _InPhaseEmitter(_PHASE_B, "bystander", phase_slot=slot)
    leaving = _LifecycleRule(_PHASE_A, "a", phase_slot=slot, transitions_to=_PHASE_B)
    _LifecycleRule(_PHASE_B, "b", phase_slot=slot)

    names = _run([bystander, leaving], ticks=4)

    # A is active on tick1 only; B is active from tick2 on (3 remaining ticks).
    assert names.count("in:bystander") == 3
    # The bystander never emits while A is the active phase.
    assert names.index("in:bystander") > names.index("tick:a")


def test_the_initial_phases_on_enter_runs_once_when_an_in_phase_rule_dispatches_first() -> None:
    # InPhaseRule registered first so it dispatches before the owner each tick:
    # the owner's on_enter must run on its behalf once, and never again.
    slot = PhaseSlot(_MACHINE_KEY, _PHASE_A)
    bystander = _InPhaseEmitter(_PHASE_A, "bystander", phase_slot=slot)
    owner = _LifecycleRule(_PHASE_A, "owner", phase_slot=slot)

    names = _run([bystander, owner], ticks=2)

    assert names.count("enter:owner") == 1


def test_the_initial_phases_on_enter_runs_before_an_earlier_registered_in_phase_rule() -> None:
    slot = PhaseSlot(_MACHINE_KEY, _PHASE_A)
    bystander = _InPhaseEmitter(_PHASE_A, "bystander", phase_slot=slot)
    owner = _LifecycleRule(_PHASE_A, "owner", phase_slot=slot)

    names = _run([bystander, owner], ticks=1)

    assert names[:2] == ["enter:owner", "in:bystander"]


def test_the_initial_phases_on_enter_runs_when_its_owner_hears_no_event() -> None:
    slot = PhaseSlot(_MACHINE_KEY, _PHASE_A)
    owner = _DeafOwner(_PHASE_A, "owner", phase_slot=slot)
    bystander = _InPhaseEmitter(_PHASE_A, "bystander", phase_slot=slot)

    names = _run([owner, bystander], ticks=1)

    assert names == ["enter:owner", "in:bystander"]


def test_the_initial_phases_on_enter_runs_when_only_another_phases_rule_hears_an_event() -> None:
    slot = PhaseSlot(_MACHINE_KEY, _PHASE_A)
    _DeafOwner(_PHASE_A, "owner", phase_slot=slot)
    other_phase = _InPhaseEmitter(_PHASE_B, "other_phase", phase_slot=slot)

    names = _run([other_phase], ticks=1)

    assert names == ["enter:owner"]


def test_multiple_in_phase_rules_share_one_phase() -> None:
    slot = PhaseSlot(_MACHINE_KEY, _PHASE_A)
    first = _InPhaseEmitter(_PHASE_A, "first", phase_slot=slot)
    second = _InPhaseEmitter(_PHASE_A, "second", phase_slot=slot)

    names = _run([first, second], ticks=1)

    assert "in:first" in names
    assert "in:second" in names


def test_in_phase_rule_and_phase_rule_coexist_on_one_phase() -> None:
    slot = PhaseSlot(_MACHINE_KEY, _PHASE_A)
    owner = _LifecycleRule(_PHASE_A, "owner", phase_slot=slot)
    bystander = _InPhaseEmitter(_PHASE_A, "bystander", phase_slot=slot)

    names = _run([owner, bystander], ticks=1)

    assert names == ["enter:owner", "tick:owner", "in:bystander"]


def test_phase_slot_reports_the_phase_rule_constructed_for_each_phase() -> None:
    slot = PhaseSlot(_MACHINE_KEY, _PHASE_A)
    a = _LifecycleRule(_PHASE_A, "a", phase_slot=slot)
    b = _LifecycleRule(_PHASE_B, "b", phase_slot=slot)

    assert slot.owner_of(_PHASE_A) is a
    assert slot.owner_of(_PHASE_B) is b


def test_constructing_a_second_owner_for_a_phase_raises_naming_the_phase() -> None:
    slot = PhaseSlot(_MACHINE_KEY, _PHASE_A)
    _LifecycleRule(_PHASE_A, "one", phase_slot=slot)

    with pytest.raises(ValueError, match="PhaseKey\\('a'\\)"):
        _LifecycleRule(_PHASE_A, "two", phase_slot=slot)


def test_registering_a_second_handler_for_an_event_type_on_a_phase_rule_raises() -> None:
    rule = _LifecycleRule(_PHASE_A, "a", phase_slot=PhaseSlot(_MACHINE_KEY, _PHASE_A))

    with pytest.raises(ValueError, match=r"_LifecycleRule.*_TickEvent"):
        rule.on(_TickEvent, lambda e, s: None)


def test_the_same_phase_may_have_an_owner_under_each_of_two_slots() -> None:
    one_slot = PhaseSlot("machine_one", _PHASE_A)
    other_slot = PhaseSlot("machine_two", _PHASE_A)
    one = _LifecycleRule(_PHASE_A, "one", phase_slot=one_slot)
    other = _LifecycleRule(_PHASE_A, "other", phase_slot=other_slot)

    assert one_slot.owner_of(_PHASE_A) is one
    assert other_slot.owner_of(_PHASE_A) is other


def test_in_phase_rules_never_own_their_phase() -> None:
    slot = PhaseSlot(_MACHINE_KEY, _PHASE_A)
    _InPhaseEmitter(_PHASE_A, "first", phase_slot=slot)
    _InPhaseEmitter(_PHASE_A, "second", phase_slot=slot)

    assert slot.owner_of(_PHASE_A) is None


def test_in_phase_rules_sharing_a_phase_leave_its_owner_in_place() -> None:
    slot = PhaseSlot(_MACHINE_KEY, _PHASE_A)
    owner = _LifecycleRule(_PHASE_A, "owner", phase_slot=slot)
    _InPhaseEmitter(_PHASE_A, "bystander", phase_slot=slot)

    assert slot.owner_of(_PHASE_A) is owner


def test_shared_phase_slot_resolves_the_same_machine_for_phase_rule_and_in_phase_rule() -> None:
    # A scene constructs exactly one PhaseSlot per machine (e.g. tag_phase) and
    # passes that same instance to every PhaseRule/InPhaseRule plus its own
    # module-level phase reference. All three must resolve the identical
    # cached PhaseMachine.
    slot = PhaseSlot(_MACHINE_KEY, _PHASE_A)
    owner = _LifecycleRule(_PHASE_A, "owner", phase_slot=slot)
    bystander = _InPhaseEmitter(_PHASE_A, "bystander", phase_slot=slot)

    state = GameState(SpyEffectControls(), SceneControls())

    via_module_level_reference = slot(state)
    via_phase_rule = _rule_machine(owner, state)
    via_in_phase_rule = _rule_machine(bystander, state)

    assert via_module_level_reference is via_phase_rule
    assert via_module_level_reference is via_in_phase_rule


def test_a_phase_rule_reads_how_long_its_phase_has_run() -> None:
    slot = PhaseSlot(_MACHINE_KEY, _PHASE_A)
    owner = _ElapsedRecordingOwner(_PHASE_A, slot, next_phase=_PHASE_B)
    _LifecycleRule(_PHASE_B, "b", phase_slot=slot)

    _run_timed([owner], ticks=2, step=0.25)

    assert owner.readings == pytest.approx([0.25, 0.5])


def test_an_in_phase_rule_reads_how_long_its_phase_has_run() -> None:
    slot = PhaseSlot(_MACHINE_KEY, _PHASE_A)
    leaving = _LifecycleRule(_PHASE_A, "a", phase_slot=slot, transitions_to=_PHASE_B)
    _LifecycleRule(_PHASE_B, "b", phase_slot=slot)
    bystander = _ElapsedRecordingBystander(_PHASE_B, slot)

    # B is entered at 0.25 s, on tick 1.
    _run_timed([leaving, bystander], ticks=3, step=0.25)

    assert bystander.readings == pytest.approx([0.25, 0.5])


def test_a_phase_rules_reading_restarts_from_zero_when_its_phase_is_re_entered() -> None:
    slot = PhaseSlot(_MACHINE_KEY, _PHASE_A)
    owner = _ElapsedRecordingOwner(_PHASE_A, slot, next_phase=_PHASE_B)
    bouncer = _LifecycleRule(_PHASE_B, "b", phase_slot=slot, transitions_to=_PHASE_A)

    # A leaves at 1.0 s (tick 2); B sends it back at 1.5 s (tick 3).
    _run_timed([owner, bouncer], ticks=4, step=0.5)

    assert owner.readings == pytest.approx([0.5, 1.0, 0.5])


def test_an_in_phase_rules_reading_restarts_from_zero_when_its_phase_is_re_entered() -> None:
    slot = PhaseSlot(_MACHINE_KEY, _PHASE_A)
    bystander = _ElapsedRecordingBystander(_PHASE_A, slot)
    owner = _ElapsedRecordingOwner(_PHASE_A, slot, next_phase=_PHASE_B)
    bouncer = _LifecycleRule(_PHASE_B, "b", phase_slot=slot, transitions_to=_PHASE_A)

    # A leaves at 1.0 s (tick 2); B sends it back at 1.5 s (tick 3).
    _run_timed([bystander, owner, bouncer], ticks=4, step=0.5)

    assert bystander.readings == pytest.approx([0.5, 1.0, 0.5])


_PHASE_C = PhaseKey("c")

_Declare = Callable[[PhaseRule, GameState], None]


class _EndsBy(PhaseRule):
    """PhaseRule whose ``on_enter`` runs *declare*, optionally transitioning on its first tick.

    With *handles_sensors*, its ``Sensors`` handler emits ``sensors:<label>``
    each time it runs.
    """

    def __init__(
        self,
        phase: PhaseKey,
        phase_slot: PhaseSlot,
        declare: _Declare,
        transitions_to: PhaseKey | None = None,
        handles_sensors: bool = False,
        label: str = "",
    ) -> None:
        super().__init__(phase, phase_slot)
        self._declare = declare
        self._transitions_to = transitions_to
        self._label = label
        if handles_sensors or transitions_to is not None:
            self.on(InputEvents.Sensors, self._sensors)

    def on_enter(self, state: GameState) -> None:
        self._declare(self, state)

    def _sensors(self, event: InputEvents.Sensors, state: GameState) -> None:
        state.effect_controls.add_effect(Scope.PERSONAL, "sensors:" + self._label, {})
        if self._transitions_to is not None:
            next_phase, self._transitions_to = self._transitions_to, None
            self.transition_to(state, next_phase)


class _AtTime(GameRule):
    """Plain rule running *action* once, on the first ``Sensors`` at or after *seconds*."""

    def __init__(self, seconds: float, action: Callable[[GameState], None]) -> None:
        self._seconds = seconds
        self._action: Callable[[GameState], None] | None = action
        self.on(InputEvents.Sensors, self._sensors)

    def _sensors(self, event: InputEvents.Sensors, state: GameState) -> None:
        if self._action is not None and state.total >= self._seconds:
            self._action(state)
            self._action = None


# Each returns an end declaration that fires at 1 s, and the rules that make
# it fire, which go before the declaring rule.
_EndingAtOneSecond = Callable[[PhaseKey], tuple[_Declare, list[GameRule]]]


def _ends_after_one_second(next_phase: PhaseKey) -> tuple[_Declare, list[GameRule]]:
    return (lambda rule, state: rule.end_after(state, 1.0, next_phase)), []


def _ends_on_a_flag_set_at_one_second(next_phase: PhaseKey) -> tuple[_Declare, list[GameRule]]:
    return (lambda rule, state: rule.end_when(state, lambda s: s.get("over", False), next_phase)), [
        _AtTime(1.0, lambda s: s.set("over", True))
    ]


def _ends_on_a_receipt_stopped_at_one_second(
    next_phase: PhaseKey,
) -> tuple[_Declare, list[GameRule]]:
    receipt = EffectReceipt(1)
    return (lambda rule, state: rule.end_when_stopped(state, receipt, next_phase)), [
        _AtTime(1.0, lambda s: receipt.stop())
    ]


_EVERY_KIND_OF_END = [
    pytest.param(_ends_after_one_second, id="duration"),
    pytest.param(_ends_on_a_flag_set_at_one_second, id="condition"),
    pytest.param(_ends_on_a_receipt_stopped_at_one_second, id="receipt"),
]


def _declare_nothing(rule: PhaseRule, state: GameState) -> None:
    pass


def _run_sensors(
    rules: list, slot: PhaseSlot, ticks: int, spy: SpyEffectControls | None = None
) -> list[PhaseKey]:
    """Run *rules* through *ticks* SceneRun ticks of 0.5 s, one ``Sensors`` each.

    Returns the active phase after each tick.
    """
    state = GameState(spy or SpyEffectControls(), SceneControls())
    run = SceneRun(state, rules)
    sensors = InputEvents.Sensors(ButtonData(states={}))
    phases = []
    for _ in range(ticks):
        state.queue_event(sensors)
        run.tick(0.5)
        phases.append(slot(state).phase)
    return phases


@pytest.mark.parametrize("ending_at_one_second", _EVERY_KIND_OF_END)
def test_a_declared_end_moves_the_phase_to_its_named_phase_on_the_tick_it_holds(
    ending_at_one_second: _EndingAtOneSecond,
) -> None:
    slot = PhaseSlot(_MACHINE_KEY, _PHASE_A)
    declare, triggers = ending_at_one_second(_PHASE_B)
    ending = _EndsBy(_PHASE_A, slot, declare)
    _DeafOwner(_PHASE_B, "b", slot)

    phases = _run_sensors([*triggers, ending], slot, ticks=3)

    assert phases == [_PHASE_A, _PHASE_B, _PHASE_B]


@pytest.mark.parametrize("ending_at_one_second", _EVERY_KIND_OF_END)
def test_a_transition_the_rule_makes_itself_cancels_its_declared_end(
    ending_at_one_second: _EndingAtOneSecond,
) -> None:
    slot = PhaseSlot(_MACHINE_KEY, _PHASE_A)
    declare, triggers = ending_at_one_second(_PHASE_B)
    ending = _EndsBy(_PHASE_A, slot, declare, transitions_to=_PHASE_C)
    _DeafOwner(_PHASE_B, "b", slot)
    next_owner = _DeafOwner(_PHASE_C, "c", slot)

    phases = _run_sensors([*triggers, ending, next_owner], slot, ticks=3)

    assert phases == [_PHASE_C, _PHASE_C, _PHASE_C]


@pytest.mark.parametrize("ending_at_one_second", _EVERY_KIND_OF_END)
def test_a_phase_re_entered_after_its_end_was_cancelled_declares_it_again(
    ending_at_one_second: _EndingAtOneSecond,
) -> None:
    slot = PhaseSlot(_MACHINE_KEY, _PHASE_A)
    declare, triggers = ending_at_one_second(_PHASE_B)
    ending = _EndsBy(_PHASE_A, slot, declare, transitions_to=_PHASE_C)
    bouncer = _EndsBy(_PHASE_C, slot, _declare_nothing, transitions_to=_PHASE_A)
    _DeafOwner(_PHASE_B, "b", slot)

    phases = _run_sensors([*triggers, ending, bouncer], slot, ticks=2)

    assert phases == [_PHASE_C, _PHASE_A]


def test_a_second_end_declared_in_one_phase_entry_raises() -> None:
    slot = PhaseSlot(_MACHINE_KEY, _PHASE_A)

    def declare_twice(rule: PhaseRule, state: GameState) -> None:
        rule.end_after(state, 1.0, _PHASE_B)
        rule.end_when(state, lambda s: False, _PHASE_B)

    ending = _EndsBy(_PHASE_A, slot, declare_twice)
    _DeafOwner(_PHASE_B, "b", slot)

    with pytest.raises(RuntimeError, match="already declared"):
        _run_sensors([ending], slot, ticks=1)


def test_declaring_an_end_from_a_handler_raises() -> None:
    slot = PhaseSlot(_MACHINE_KEY, _PHASE_A)
    _DeafOwner(_PHASE_B, "b", slot)

    class _DeclaresFromHandler(PhaseRule):
        def __init__(self) -> None:
            super().__init__(_PHASE_A, slot)
            self.on(InputEvents.Sensors, self._sensors)

        def _sensors(self, event: InputEvents.Sensors, state: GameState) -> None:
            self.end_after(state, 1.0, _PHASE_B)

    with pytest.raises(RuntimeError, match="outside its on_enter"):
        _run_sensors([_DeclaresFromHandler()], slot, ticks=1)


def test_declaring_an_end_from_another_phases_on_enter_raises() -> None:
    slot = PhaseSlot(_MACHINE_KEY, _PHASE_A)
    _DeafOwner(_PHASE_C, "c", slot)
    bystander = _EndsBy(_PHASE_B, slot, _declare_nothing)
    reaches_over = _EndsBy(
        _PHASE_A, slot, lambda rule, state: bystander.end_after(state, 1.0, _PHASE_C)
    )

    with pytest.raises(RuntimeError, match="outside its on_enter"):
        _run_sensors([reaches_over], slot, ticks=1)


def test_in_phase_rules_cannot_declare_an_end() -> None:
    bystander = _InPhaseEmitter(_PHASE_A, "bystander", PhaseSlot(_MACHINE_KEY, _PHASE_A))

    assert not hasattr(bystander, "end_when")
    assert not hasattr(bystander, "end_after")
    assert not hasattr(bystander, "end_when_stopped")


def test_a_declared_end_fires_before_the_rules_sensors_handler_which_skips_that_tick() -> None:
    slot = PhaseSlot(_MACHINE_KEY, _PHASE_A)
    spy = SpyEffectControls()
    declare, _ = _ends_after_one_second(_PHASE_B)
    ending = _EndsBy(_PHASE_A, slot, declare, handles_sensors=True, label="a")
    _DeafOwner(_PHASE_B, "b", slot)

    phases = _run_sensors([ending], slot, ticks=3, spy=spy)

    assert phases == [_PHASE_A, _PHASE_B, _PHASE_B]
    assert [name for _, name, _ in spy.add_effect_calls] == ["sensors:a", "enter:b"]


def test_cancelling_an_end_declared_on_a_receipt_leaves_its_effect_running() -> None:
    slot = PhaseSlot(_MACHINE_KEY, _PHASE_A)
    spy = SpyEffectControls()
    receipt = EffectReceipt(1)
    ending = _EndsBy(
        _PHASE_A,
        slot,
        lambda rule, state: rule.end_when_stopped(state, receipt, _PHASE_B),
        transitions_to=_PHASE_C,
    )
    _DeafOwner(_PHASE_B, "b", slot)
    _DeafOwner(_PHASE_C, "c", slot)

    _run_sensors([ending], slot, ticks=2, spy=spy)

    assert not receipt.is_stopped()
    assert spy.stop_effect_calls == []

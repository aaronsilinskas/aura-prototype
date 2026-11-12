import tracemalloc

from engine.engine import GameRule
from engine.events import Event, EventGroup
from engine.state import EffectControls, GameState, SceneControls, SceneRun

_GROUP = EventGroup("test")


def _make_state() -> GameState:
    return GameState(EffectControls(), SceneControls())


class _RecordingRule(GameRule):
    """Appends ``(name, event)`` to a shared log for every event it hears."""

    def __init__(self, name: str, log: list[tuple[str, Event]]) -> None:
        self._name = name
        self._log = log

    def handle_event(self, event: Event, state: GameState) -> None:
        self._log.append((self._name, event))


def test_tick_dispatches_each_queued_event_to_every_rule_in_order() -> None:
    log: list[tuple[str, Event]] = []
    state = _make_state()
    run = SceneRun(state, [_RecordingRule("first", log), _RecordingRule("second", log)])
    a = Event(_GROUP, "a")
    b = Event(_GROUP, "b")
    state.queue_event(a)
    state.queue_event(b)

    run.tick(0.0)

    assert log == [("first", a), ("second", a), ("first", b), ("second", b)]


class _ChainRule(GameRule):
    """Queues *follow_up* whenever it hears *trigger*, and logs every event."""

    def __init__(self, trigger: Event, follow_up: Event) -> None:
        self._trigger = trigger
        self._follow_up = follow_up
        self.heard: list[Event] = []

    def handle_event(self, event: Event, state: GameState) -> None:
        self.heard.append(event)
        if event is self._trigger:
            state.queue_event(self._follow_up)


def test_an_event_queued_during_dispatch_is_dispatched_in_the_same_tick() -> None:
    trigger = Event(_GROUP, "trigger")
    follow_up = Event(_GROUP, "follow_up")
    rule = _ChainRule(trigger, follow_up)
    state = _make_state()
    run = SceneRun(state, [rule])
    state.queue_event(trigger)

    run.tick(0.0)

    assert rule.heard == [trigger, follow_up]


def test_an_event_dispatched_in_one_tick_is_not_dispatched_again_in_the_next() -> None:
    log: list[tuple[str, Event]] = []
    state = _make_state()
    run = SceneRun(state, [_RecordingRule("rule", log)])
    event = Event(_GROUP, "once")
    state.queue_event(event)

    run.tick(0.0)
    run.tick(0.0)

    assert log == [("rule", event)]


def test_tick_dispatches_every_event_queued_beyond_the_initial_capacity_in_order() -> None:
    log: list[tuple[str, Event]] = []
    state = GameState(EffectControls(), SceneControls(), queue_capacity=2)
    run = SceneRun(state, [_RecordingRule("rule", log)])
    events = [Event(_GROUP, str(i)) for i in range(5)]
    for event in events:
        state.queue_event(event)

    run.tick(0.0)

    assert log == [("rule", event) for event in events]


class _ReadingRule(GameRule):
    """Records ``(elapsed, total, dispatch_count)`` as read inside each handler call."""

    def __init__(self) -> None:
        self.seen: list[tuple[float, float, int]] = []

    def handle_event(self, event: Event, state: GameState) -> None:
        self.seen.append((state.elapsed, state.total, state.dispatch_count))


def test_handlers_read_this_ticks_elapsed_and_the_running_total() -> None:
    rule = _ReadingRule()
    state = _make_state()
    run = SceneRun(state, [rule])
    event = Event(_GROUP, "frame")

    for elapsed in (0.25, 0.5, 0.125):
        state.queue_event(event)
        run.tick(elapsed)

    assert [(e, t) for e, t, _ in rule.seen] == [(0.25, 0.25), (0.5, 0.75), (0.125, 0.875)]


def test_dispatch_count_rises_by_one_per_event_including_a_reused_event_object() -> None:
    rule = _ReadingRule()
    state = _make_state()
    run = SceneRun(state, [rule, rule])
    reused = Event(_GROUP, "reused")

    state.queue_event(reused)
    state.queue_event(Event(_GROUP, "other"))
    run.tick(0.0)
    state.queue_event(reused)
    run.tick(0.0)

    assert [count for _, _, count in rule.seen] == [1, 1, 2, 2, 3, 3]


def test_steady_state_ticking_does_not_grow_the_queue() -> None:
    state = _make_state()
    run = SceneRun(state, [GameRule()])
    event = Event(_GROUP, "frame")
    state.queue_event(event)
    run.tick(0.0)  # warm up: first-call allocations are not steady state

    tracemalloc.start()
    try:
        before, _ = tracemalloc.get_traced_memory()
        for _ in range(1000):
            state.queue_event(event)
            run.tick(0.0)
        after, _ = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    # A queue that kept one more slot per tick would hold ~8 KB more here.
    assert after - before < 1024

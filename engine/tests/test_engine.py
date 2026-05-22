import pytest

from engine.effects.manager import EffectControls
from engine.engine import GameEngine, GameRule, GameState, Version
from engine.events import Event, EventGroup
from engine.scene import SceneControls
from engine.timer import Timer

_GROUP = EventGroup("test")


class _AEvent(Event):
    __slots__ = ()

    def __init__(self) -> None:
        super().__init__(_GROUP, "a")


class _BEvent(Event):
    __slots__ = ()

    def __init__(self) -> None:
        super().__init__(_GROUP, "b")


def _make_effect_controls() -> EffectControls:
    return EffectControls()


def _make_scene_controls() -> SceneControls:
    return SceneControls()


def _make_state() -> GameState:
    controls = _make_effect_controls()
    return GameState(controls, _make_scene_controls())


class _CapturingRule(GameRule):
    def __init__(self) -> None:
        super().__init__("test.capturing_rule", Version(1, 0))
        self.captured_controls: list = []

    def handle_event(self, event: Event, state: GameState) -> None:
        self.captured_controls.append(state.effect_controls)


# ---------------------------------------------------------------------------
# GameState.effect_controls
# ---------------------------------------------------------------------------


def test_rule_receives_the_effect_controls_passed_to_the_engine() -> None:
    controls = _make_effect_controls()
    rule = _CapturingRule()
    engine = GameEngine(effect_controls=controls)
    state = engine.create_state(_make_scene_controls())
    engine.add_rules(rule)
    state.queue_event(Event(_GROUP, "test"))

    engine.update(state)

    assert rule.captured_controls[0] is controls


# ---------------------------------------------------------------------------
# GameRule.on — event type dispatch
# ---------------------------------------------------------------------------


def test_registered_handler_fires_when_matching_event_is_dispatched() -> None:
    captured = []
    rule = GameRule("test", Version(1, 0))
    rule.on(_AEvent, lambda e, s: captured.append(e))

    event = _AEvent()
    rule.handle_event(event, _make_state())

    assert captured == [event]


def test_unregistered_event_type_is_silently_ignored() -> None:
    captured = []
    rule = GameRule("test", Version(1, 0))
    rule.on(_AEvent, lambda e, s: captured.append(e))

    rule.handle_event(_BEvent(), _make_state())

    assert captured == []


def test_each_event_type_routes_to_its_own_registered_handler() -> None:
    a_captured = []
    b_captured = []
    rule = GameRule("test", Version(1, 0))
    rule.on(_AEvent, lambda e, s: a_captured.append(e))
    rule.on(_BEvent, lambda e, s: b_captured.append(e))

    a_event = _AEvent()
    b_event = _BEvent()
    rule.handle_event(a_event, _make_state())
    rule.handle_event(b_event, _make_state())

    assert a_captured == [a_event]
    assert b_captured == [b_event]


# ---------------------------------------------------------------------------
# GameState.elapsed / GameState.total — read-only time properties
# ---------------------------------------------------------------------------


class _TimeCaptureRule(GameRule):
    """Records elapsed and total seen during handle_event."""

    def __init__(self) -> None:
        super().__init__("test.time_capture", Version(1, 0))
        self.seen_elapsed: list[float] = []
        self.seen_total: list[float] = []

    def handle_event(self, event: Event, state: GameState) -> None:
        self.seen_elapsed.append(state.elapsed)
        self.seen_total.append(state.total)


class _ControlledTimer(Timer):
    """Timer whose elapsed/total values are set directly for deterministic tests."""

    def __init__(self, elapsed: float = 0.0, total: float = 0.0) -> None:
        super().__init__()
        self.elapsed = elapsed
        self.total = total

    def update(self) -> None:
        pass  # values remain whatever was set at construction / by the test


def test_elapsed_is_read_only() -> None:
    state = _make_state()

    with pytest.raises(AttributeError):
        state.elapsed = 1.0  # type: ignore[misc]


def test_total_is_read_only() -> None:
    state = _make_state()

    with pytest.raises(AttributeError):
        state.total = 1.0  # type: ignore[misc]


def test_state_elapsed_and_total_reflect_timer_values_after_engine_update() -> None:
    timer = _ControlledTimer(elapsed=0.016, total=1.5)
    engine = GameEngine(effect_controls=_make_effect_controls(), timer=timer)
    state = engine.create_state(_make_scene_controls())

    engine.update(state)

    assert state.elapsed == pytest.approx(0.016)
    assert state.total == pytest.approx(1.5)


def test_rules_see_elapsed_and_total_time_from_the_engines_timer() -> None:
    timer = _ControlledTimer(elapsed=0.032, total=2.0)
    engine = GameEngine(effect_controls=_make_effect_controls(), timer=timer)
    state = engine.create_state(_make_scene_controls())
    rule = _TimeCaptureRule()
    engine.add_rules(rule)
    state.queue_event(Event(_GROUP, "tick"))

    engine.update(state)

    assert rule.seen_elapsed == [pytest.approx(0.032)]
    assert rule.seen_total == [pytest.approx(2.0)]


# ---------------------------------------------------------------------------
# GameState.data — persistent data dict
# ---------------------------------------------------------------------------


def test_state_data_is_empty_when_no_initial_data_is_provided() -> None:
    state = _make_state()

    assert state.data == {}


def test_state_can_be_constructed_standalone_with_preset_data_for_rule_unit_testing() -> None:
    controls = _make_effect_controls()

    state = GameState(controls, _make_scene_controls(), {"key": "val"})

    assert state.data["key"] == "val"


def test_rules_cannot_access_game_engine_through_state() -> None:
    state = _make_state()

    assert not hasattr(state, "engine")


# ---------------------------------------------------------------------------
# GameEngine.create_state — factory wires effect_controls and scene_controls
# ---------------------------------------------------------------------------


def test_create_state_wires_engine_effect_controls() -> None:
    controls = _make_effect_controls()
    engine = GameEngine(effect_controls=controls)

    state = engine.create_state(_make_scene_controls())

    assert state.effect_controls is controls


def test_create_state_wires_scene_controls() -> None:
    engine = GameEngine(effect_controls=_make_effect_controls())
    scene_controls = _make_scene_controls()

    state = engine.create_state(scene_controls)

    assert state.scene_controls is scene_controls


def test_create_state_seeds_data_from_initial_data() -> None:
    engine = GameEngine(effect_controls=_make_effect_controls())

    state = engine.create_state(_make_scene_controls(), initial_data={"score": 0})

    assert state.data["score"] == 0


def test_create_state_returns_empty_data_when_no_initial_data_provided() -> None:
    engine = GameEngine(effect_controls=_make_effect_controls())

    state = engine.create_state(_make_scene_controls())

    assert state.data == {}


# ---------------------------------------------------------------------------
# GameEngine.update(state) — stateless tick
# ---------------------------------------------------------------------------


def test_data_written_in_one_tick_is_readable_in_a_later_tick() -> None:
    class _CounterRule(GameRule):
        def __init__(self) -> None:
            super().__init__("test.counter", Version(1, 0))

        def handle_event(self, event: Event, state: GameState) -> None:
            state.data["n"] = state.data.get("n", 0) + 1

    engine = GameEngine(effect_controls=_make_effect_controls())
    state = engine.create_state(_make_scene_controls())
    engine.add_rules(_CounterRule())

    state.queue_event(Event(_GROUP, "tick"))
    engine.update(state)
    state.queue_event(Event(_GROUP, "tick"))
    engine.update(state)

    assert state.data["n"] == 2


def test_data_written_by_an_earlier_rule_is_visible_to_a_later_rule_in_the_same_tick() -> None:
    class _WriterRule(GameRule):
        def __init__(self) -> None:
            super().__init__("test.writer", Version(1, 0))

        def handle_event(self, event: Event, state: GameState) -> None:
            state.data["shared"] = 42

    class _ReaderRule(GameRule):
        def __init__(self) -> None:
            super().__init__("test.reader", Version(1, 0))
            self.value = None

        def handle_event(self, event: Event, state: GameState) -> None:
            self.value = state.data.get("shared")

    engine = GameEngine(effect_controls=_make_effect_controls())
    state = engine.create_state(_make_scene_controls())
    reader = _ReaderRule()
    engine.add_rules(_WriterRule(), reader)
    state.queue_event(Event(_GROUP, "tick"))

    engine.update(state)

    assert reader.value == 42


def test_different_state_objects_are_independent() -> None:
    class _CounterRule(GameRule):
        def __init__(self) -> None:
            super().__init__("test.counter", Version(1, 0))

        def handle_event(self, event: Event, state: GameState) -> None:
            state.data["n"] = state.data.get("n", 0) + 1

    engine = GameEngine(effect_controls=_make_effect_controls())
    state_a = engine.create_state(_make_scene_controls())
    state_b = engine.create_state(_make_scene_controls())
    engine.add_rules(_CounterRule())

    state_a.queue_event(Event(_GROUP, "tick"))
    engine.update(state_a)
    state_a.queue_event(Event(_GROUP, "tick"))
    engine.update(state_a)

    state_b.queue_event(Event(_GROUP, "tick"))
    engine.update(state_b)

    assert state_a.data["n"] == 2
    assert state_b.data["n"] == 1


# ---------------------------------------------------------------------------
# GameState.queue_event — rules enqueue without a GameEngine reference
# ---------------------------------------------------------------------------


def test_event_queued_from_state_inside_a_rule_is_dispatched_in_the_same_update() -> None:
    captured: list[Event] = []

    class _RelayRule(GameRule):
        def __init__(self) -> None:
            super().__init__("test.relay", Version(1, 0))

        def handle_event(self, event: Event, state: GameState) -> None:
            if event.name == "trigger":
                state.queue_event(Event(_GROUP, "relayed"))
            elif event.name == "relayed":
                captured.append(event)

    engine = GameEngine(effect_controls=_make_effect_controls())
    state = engine.create_state(_make_scene_controls())
    engine.add_rules(_RelayRule())
    state.queue_event(Event(_GROUP, "trigger"))

    engine.update(state)

    assert captured[0].name == "relayed"


# ---------------------------------------------------------------------------
# GameState.clear_queue — discard pending events
# ---------------------------------------------------------------------------


def test_clear_queue_prevents_events_from_being_dispatched() -> None:
    captured: list[Event] = []

    class _CaptureRule(GameRule):
        def __init__(self) -> None:
            super().__init__("test.capture", Version(1, 0))

        def handle_event(self, event: Event, state: GameState) -> None:
            captured.append(event)

    engine = GameEngine(effect_controls=_make_effect_controls())
    state = engine.create_state(_make_scene_controls())
    engine.add_rules(_CaptureRule())
    state.queue_event(Event(_GROUP, "should-not-fire"))
    state.clear_queue()

    engine.update(state)

    assert captured == []


# ---------------------------------------------------------------------------
# GameState.scene_controls — scene transition interface
# ---------------------------------------------------------------------------


def test_state_exposes_scene_controls_passed_at_construction() -> None:
    scene_controls = _make_scene_controls()

    state = GameState(_make_effect_controls(), scene_controls)

    assert state.scene_controls is scene_controls


def test_scene_controls_default_raises_not_implemented_on_load() -> None:
    sc = SceneControls()

    with pytest.raises(NotImplementedError):
        sc.load("some-scene")


def test_scene_controls_default_raises_not_implemented_on_overlay() -> None:
    sc = SceneControls()

    with pytest.raises(NotImplementedError):
        sc.overlay("some-scene")


def test_scene_controls_default_raises_not_implemented_on_pop() -> None:
    sc = SceneControls()

    with pytest.raises(NotImplementedError):
        sc.pop()


# ---------------------------------------------------------------------------
# GameEngine.set_rules — full rule list replacement
# ---------------------------------------------------------------------------


def test_set_rules_replaces_existing_rules() -> None:
    old_captured: list[Event] = []
    new_captured: list[Event] = []

    class _OldRule(GameRule):
        def __init__(self) -> None:
            super().__init__("test.old", Version(1, 0))

        def handle_event(self, event: Event, state: GameState) -> None:
            old_captured.append(event)

    class _NewRule(GameRule):
        def __init__(self) -> None:
            super().__init__("test.new", Version(1, 0))

        def handle_event(self, event: Event, state: GameState) -> None:
            new_captured.append(event)

    engine = GameEngine(effect_controls=_make_effect_controls())
    engine.add_rules(_OldRule())
    engine.set_rules([_NewRule()])

    state = engine.create_state(_make_scene_controls())
    state.queue_event(Event(_GROUP, "tick"))
    engine.update(state)

    assert old_captured == []
    assert len(new_captured) == 1


def test_set_rules_with_empty_list_clears_all_rules() -> None:
    captured: list[Event] = []

    class _CaptureRule(GameRule):
        def __init__(self) -> None:
            super().__init__("test.capture", Version(1, 0))

        def handle_event(self, event: Event, state: GameState) -> None:
            captured.append(event)

    engine = GameEngine(effect_controls=_make_effect_controls())
    engine.add_rules(_CaptureRule())
    engine.set_rules([])

    state = engine.create_state(_make_scene_controls())
    state.queue_event(Event(_GROUP, "tick"))
    engine.update(state)

    assert captured == []


def test_add_rules_appends_after_set_rules() -> None:
    captured: list[Event] = []

    class _CaptureRule(GameRule):
        def __init__(self) -> None:
            super().__init__("test.capture", Version(1, 0))

        def handle_event(self, event: Event, state: GameState) -> None:
            captured.append(event)

    engine = GameEngine(effect_controls=_make_effect_controls())
    engine.set_rules([])
    engine.add_rules(_CaptureRule())

    state = engine.create_state(_make_scene_controls())
    state.queue_event(Event(_GROUP, "tick"))
    engine.update(state)

    assert len(captured) == 1

from engine.effects.manager import EffectControls
from engine.engine import GameEngine, GameRule, GameState, Version
from engine.events import Event, EventGroup
from engine.timer import Timer

import pytest

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


def _make_state() -> GameState:
    controls = _make_effect_controls()
    engine = GameEngine(effect_controls=controls)
    return GameState(engine, controls)


class _CapturingRule(GameRule):
    def __init__(self) -> None:
        super().__init__("test.capturing_rule", Version(1, 0))
        self.captured_controls: list = []

    def handle_event(self, event: Event, state: GameState) -> None:
        self.captured_controls.append(state.effect_controls)


# ---------------------------------------------------------------------------
# GameState.effect_controls
# ---------------------------------------------------------------------------


def test_game_state_carries_effect_controls_from_engine() -> None:
    controls = _make_effect_controls()
    rule = _CapturingRule()
    engine = GameEngine(effect_controls=controls)
    engine.add_rules(rule)
    engine.queue_event(Event(_GROUP, "test"))

    engine.update()

    assert rule.captured_controls[0] is controls


# ---------------------------------------------------------------------------
# GameRule.on — event type dispatch
# ---------------------------------------------------------------------------


def test_game_rule_calls_registered_handler_when_event_type_matches() -> None:
    captured = []
    rule = GameRule("test", Version(1, 0))
    rule.on(_AEvent, lambda e, s: captured.append(e))

    event = _AEvent()
    rule.handle_event(event, _make_state())

    assert captured == [event]


def test_game_rule_ignores_event_when_no_handler_registered_for_type() -> None:
    captured = []
    rule = GameRule("test", Version(1, 0))
    rule.on(_AEvent, lambda e, s: captured.append(e))

    rule.handle_event(_BEvent(), _make_state())

    assert captured == []


def test_game_rule_calls_matching_handler_among_multiple_registered_types() -> None:
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


def test_game_state_elapsed_is_read_only() -> None:
    state = _make_state()

    with pytest.raises(AttributeError):
        state.elapsed = 1.0  # type: ignore[misc]


def test_game_state_total_is_read_only() -> None:
    state = _make_state()

    with pytest.raises(AttributeError):
        state.total = 1.0  # type: ignore[misc]


def test_game_state_update_time_refreshes_elapsed_and_total() -> None:
    state = _make_state()

    state._update_time(0.016, 1.5)

    assert state.elapsed == pytest.approx(0.016)
    assert state.total == pytest.approx(1.5)


def test_game_engine_update_advances_time_seen_by_rules() -> None:
    timer = _ControlledTimer(elapsed=0.032, total=2.0)
    engine = GameEngine(effect_controls=_make_effect_controls(), timer=timer)
    rule = _TimeCaptureRule()
    engine.add_rules(rule)
    engine.queue_event(Event(_GROUP, "tick"))

    engine.update()

    assert rule.seen_elapsed == [pytest.approx(0.032)]
    assert rule.seen_total == [pytest.approx(2.0)]


def test_game_engine_uses_injected_timer_to_control_state_time() -> None:
    timer = _ControlledTimer(elapsed=0.1, total=5.0)
    engine = GameEngine(effect_controls=_make_effect_controls(), timer=timer)
    rule = _TimeCaptureRule()
    engine.add_rules(rule)
    engine.queue_event(Event(_GROUP, "tick"))

    engine.update()

    assert rule.seen_elapsed[0] == pytest.approx(0.1)
    assert rule.seen_total[0] == pytest.approx(5.0)

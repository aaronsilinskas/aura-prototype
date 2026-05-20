from engine.effects.manager import EffectControls
from engine.engine import GameEngine, GameRule, GameState, Version
from engine.events import Event, EventGroup
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


def _make_timer() -> Timer:
    return Timer()


def _make_state() -> GameState:
    controls = _make_effect_controls()
    engine = GameEngine(effect_controls=controls)
    return GameState(engine, _make_timer(), controls)


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

    engine.update(_make_timer())

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

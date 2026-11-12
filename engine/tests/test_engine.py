from engine.engine import GameRule
from engine.events import Event, EventGroup
from engine.state import EffectControls, GameState, SceneControls

_GROUP = EventGroup("test")


class _AEvent(Event):
    __slots__ = ()

    def __init__(self) -> None:
        super().__init__(_GROUP, "a")


class _BEvent(Event):
    __slots__ = ()

    def __init__(self) -> None:
        super().__init__(_GROUP, "b")


def _make_state() -> GameState:
    return GameState(EffectControls(), SceneControls())


# ---------------------------------------------------------------------------
# GameRule.on — event type dispatch
# ---------------------------------------------------------------------------


def test_registered_handler_fires_when_matching_event_is_dispatched() -> None:
    captured = []
    rule = GameRule()
    rule.on(_AEvent, lambda e, s: captured.append(e))

    event = _AEvent()
    rule.handle_event(event, _make_state())

    assert captured == [event]


def test_unregistered_event_type_is_silently_ignored() -> None:
    captured = []
    rule = GameRule()
    rule.on(_AEvent, lambda e, s: captured.append(e))

    rule.handle_event(_BEvent(), _make_state())

    assert captured == []


def test_each_event_type_routes_to_its_own_registered_handler() -> None:
    a_captured = []
    b_captured = []
    rule = GameRule()
    rule.on(_AEvent, lambda e, s: a_captured.append(e))
    rule.on(_BEvent, lambda e, s: b_captured.append(e))

    a_event = _AEvent()
    b_event = _BEvent()
    rule.handle_event(a_event, _make_state())
    rule.handle_event(b_event, _make_state())

    assert a_captured == [a_event]
    assert b_captured == [b_event]


def test_registering_a_second_handler_for_an_event_type_replaces_the_first() -> None:
    first_captured = []
    second_captured = []
    rule = GameRule()
    rule.on(_AEvent, lambda e, s: first_captured.append(e))
    rule.on(_AEvent, lambda e, s: second_captured.append(e))

    event = _AEvent()
    rule.handle_event(event, _make_state())

    assert first_captured == []
    assert second_captured == [event]

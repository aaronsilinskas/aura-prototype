from engine.events import Event, EventGroup
from engine.input import ButtonData, InputEvents
from packs.rules.conftest import EngineFixture
from packs.rules.debug.button_events import ButtonEventsRule

_GROUP = EventGroup("test")


def _make_input(states: dict[str, int]) -> InputEvents.ButtonAndMovement:
    return InputEvents.ButtonAndMovement(ButtonData(states=states))


def test_button_pressed_state_triggers_mapped_event(fixture: EngineFixture):
    triggered = Event(_GROUP, "pressed")
    fixture.game_engine.add_rules(ButtonEventsRule(button_pressed={"A": triggered}))

    fixture.state.queue_event(_make_input({"A": ButtonData.PRESSED}))
    fixture.update_engine()

    assert triggered in fixture.captured_events


def test_button_down_state_triggers_mapped_event(fixture: EngineFixture):
    triggered = Event(_GROUP, "down")
    fixture.game_engine.add_rules(ButtonEventsRule(button_down={"A": triggered}))

    fixture.state.queue_event(_make_input({"A": ButtonData.DOWN}))
    fixture.update_engine()

    assert triggered in fixture.captured_events


def test_button_up_state_triggers_mapped_event(fixture: EngineFixture):
    triggered = Event(_GROUP, "up")
    fixture.game_engine.add_rules(ButtonEventsRule(button_up={"A": triggered}))

    fixture.state.queue_event(_make_input({"A": ButtonData.UP}))
    fixture.update_engine()

    assert triggered in fixture.captured_events


def test_button_released_state_triggers_mapped_event(fixture: EngineFixture):
    triggered = Event(_GROUP, "released")
    fixture.game_engine.add_rules(ButtonEventsRule(button_released={"A": triggered}))

    fixture.state.queue_event(_make_input({"A": ButtonData.RELEASED}))
    fixture.update_engine()

    assert triggered in fixture.captured_events


def test_button_state_does_not_trigger_event_for_different_state(fixture: EngineFixture):
    should_not_trigger = Event(_GROUP, "should_not_trigger")
    fixture.game_engine.add_rules(ButtonEventsRule(button_pressed={"A": should_not_trigger}))

    fixture.state.queue_event(_make_input({"A": ButtonData.DOWN}))
    fixture.update_engine()

    assert should_not_trigger not in fixture.captured_events


def test_multiple_pressed_buttons_each_trigger_their_mapped_event(fixture: EngineFixture):
    event_1 = Event(_GROUP, "P1_pressed")
    event_2 = Event(_GROUP, "P2_pressed")
    fixture.game_engine.add_rules(ButtonEventsRule(button_pressed={"P1": event_1, "P2": event_2}))

    fixture.state.queue_event(_make_input({"P1": ButtonData.PRESSED, "P2": ButtonData.PRESSED}))
    fixture.update_engine()

    assert event_1 in fixture.captured_events
    assert event_2 in fixture.captured_events


def test_unmapped_button_does_not_trigger_any_event(fixture: EngineFixture):
    triggered = Event(_GROUP, "triggered")
    fixture.game_engine.add_rules(ButtonEventsRule(button_pressed={"A": triggered}))

    fixture.state.queue_event(_make_input({"B": ButtonData.PRESSED}))
    fixture.update_engine()

    assert triggered not in fixture.captured_events

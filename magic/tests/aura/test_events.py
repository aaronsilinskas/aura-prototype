from unittest.mock import Mock
import pytest
from pytest_mock import MockerFixture
from magic.aura import (
    Aura,
    AuraEvent,
    DamageEvent,
    HealEvent,
    CastEvent,
    AddSpellEvent,
    RemoveSpellEvent,
    EventListener,
    Spell,
)
from magic.tests.helpers import AuraFixture, MockEventListener


class EventsFixture(AuraFixture):
    def __init__(self) -> None:
        super().__init__()
        self.dummy_spell = Spell([])
        self.listener = MockEventListener()
        self.aura.event_listeners.append(self.listener)


@pytest.fixture
def fixture() -> EventsFixture:
    return EventsFixture()


# AuraEvent Base Class Tests


def test_aura_event_initialization():
    """Test that AuraEvent initializes with is_canceled as False."""
    event = AuraEvent()

    assert event.is_canceled is False


def test_aura_event_can_be_canceled():
    """Test that an AuraEvent can be canceled."""
    event = AuraEvent()

    event.is_canceled = True

    assert event.is_canceled is True


def test_aura_event_can_be_uncanceled():
    """Test that a canceled AuraEvent can be uncanceled."""
    event = AuraEvent()

    event.is_canceled = True
    event.is_canceled = False

    assert event.is_canceled is False


# DamageEvent Tests


def test_damage_event_initialization():
    """Test DamageEvent initialization with a positive amount."""
    event = DamageEvent(amount=50.0)

    assert event.amount == 50.0
    assert event.is_canceled is False


def test_damage_event_negative_amount_clamped():
    """Test that DamageEvent clamps negative amounts to zero."""
    event = DamageEvent(amount=-10.0)

    assert event.amount == 0.0


def test_damage_event_zero_amount():
    """Test DamageEvent with zero amount."""
    event = DamageEvent(amount=0.0)

    assert event.amount == 0.0


def test_damage_event_can_be_modified():
    """Test that DamageEvent amount can be modified after creation."""
    event = DamageEvent(amount=50.0)

    event.amount = 30.0

    assert event.amount == 30.0


# EventListener Tests


def test_event_listener_receives_damage_event(fixture):
    """Test that event listener receives DamageEvent."""
    listener = fixture.listener
    event = DamageEvent(amount=10.0)

    fixture.aura.process_event(event)

    assert len(listener.events) == 1
    assert listener.was_event_received(fixture.aura, event)


def test_event_listener_receives_heal_event(fixture):
    """Test that event listener receives HealEvent."""
    listener = fixture.listener
    event = HealEvent(amount=15.0)

    fixture.aura.process_event(event)

    assert len(listener.events) == 1
    assert listener.was_event_received(fixture.aura, event)


def test_event_listener_receives_add_spell_event(fixture):
    """Test that event listener receives AddSpellEvent."""
    listener = fixture.listener

    fixture.aura.add_spell(fixture.dummy_spell)

    assert len(listener.events) == 1
    event = listener.last_event
    assert isinstance(event, AddSpellEvent)
    assert event.spell is fixture.dummy_spell


def test_event_listener_receives_remove_spell_event(fixture):
    """Test that event listener receives RemoveSpellEvent."""
    listener = fixture.listener
    fixture.aura.add_spell(fixture.dummy_spell)
    listener.events.clear()  # Clear the AddSpellEvent

    fixture.aura.remove_spell(fixture.dummy_spell)

    assert len(listener.events) == 1
    event = listener.last_event
    assert isinstance(event, RemoveSpellEvent)
    assert event.spell is fixture.dummy_spell


def test_event_listener_receives_cast_event(fixture):
    """Test that event listener receives CastEvent."""
    listener = fixture.listener

    fixture.aura.cast_spell(fixture.dummy_spell)

    assert len(listener.events) == 1
    event = listener.last_event
    assert isinstance(event, CastEvent)
    assert event.spell is fixture.dummy_spell


def test_multiple_event_listeners(fixture):
    """Test that multiple event listeners all receive events."""
    listener1 = MockEventListener()
    listener2 = MockEventListener()
    fixture.aura.event_listeners.append(listener1)
    fixture.aura.event_listeners.append(listener2)
    event = DamageEvent(amount=10.0)

    fixture.aura.process_event(event)

    assert len(listener1.events) == 1
    assert len(listener2.events) == 1
    assert listener1.was_event_received(fixture.aura, event)
    assert listener2.was_event_received(fixture.aura, event)


def test_event_listener_not_called_if_event_canceled(fixture):
    """Test that event listeners are not called if event is canceled."""
    listener = fixture.listener

    class CancelingSpell(Spell):
        def __init__(self):
            super().__init__([])

        def update(self, aura: Aura, elapsed_time: float) -> bool:
            return False

        def modify_event(self, aura: Aura, event: AuraEvent) -> None:
            event.is_canceled = True

    canceling_spell = CancelingSpell()
    fixture.aura.add_spell(canceling_spell)

    listener.events.clear()  # Clear AddSpellEvent
    fixture.aura.process_event(DamageEvent(amount=10.0))

    # Event was canceled, so listener should not be notified
    assert len(listener.events) == 0


def test_event_listener_receives_events_in_order(fixture):
    """Test that event listeners receive multiple events in order."""
    listener = fixture.listener

    event1 = DamageEvent(amount=10.0)
    event2 = HealEvent(amount=5.0)
    event3 = DamageEvent(amount=3.0)

    fixture.aura.process_event(event1)
    fixture.aura.process_event(event2)
    fixture.aura.process_event(event3)

    assert len(listener.events) == 3
    assert listener.events[0][1] is event1
    assert listener.events[1][1] is event2
    assert listener.events[2][1] is event3


def test_event_listener_can_inspect_aura_state(fixture):
    """Test that event listener can inspect aura state when event occurs."""
    initial_magic = fixture.aura.magic.value
    listener = fixture.listener

    fixture.aura.process_event(DamageEvent(amount=10.0))

    # Listener receives aura reference and can check state
    aura_from_event = listener.events[0][0]
    assert aura_from_event.magic.value == initial_magic - 10.0


def test_event_listeners_can_be_removed_from_list(fixture):
    """Test that event listeners can be removed from the list."""
    listener = MockEventListener()
    fixture.aura.event_listeners.append(listener)

    fixture.aura.event_listeners.remove(listener)

    assert listener not in fixture.aura.event_listeners

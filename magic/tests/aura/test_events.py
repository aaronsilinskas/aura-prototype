import pytest

from magic.aura import (
    AddSpellEvent,
    Aura,
    AuraEvent,
    CastEvent,
    DamageEvent,
    HealEvent,
    RemoveSpellEvent,
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


def test_aura_event_initialization():
    event = AuraEvent()

    assert event.is_canceled is False


def test_aura_event_can_be_canceled():
    event = AuraEvent()

    event.is_canceled = True

    assert event.is_canceled is True


def test_aura_event_can_be_uncanceled():
    event = AuraEvent()

    event.is_canceled = True
    event.is_canceled = False

    assert event.is_canceled is False


def test_damage_event_initialization():
    event = DamageEvent(amount=50.0)

    assert event.amount == 50.0
    assert event.is_canceled is False


def test_damage_event_negative_amount_clamped():
    event = DamageEvent(amount=-10.0)

    assert event.amount == 0.0


def test_damage_event_zero_amount():
    event = DamageEvent(amount=0.0)

    assert event.amount == 0.0


def test_damage_event_can_be_modified():
    event = DamageEvent(amount=50.0)

    event.amount = 30.0

    assert event.amount == 30.0


def test_event_listener_receives_damage_event(fixture):
    listener = fixture.listener
    event = DamageEvent(amount=10.0)

    fixture.aura.process_event(event)

    assert len(listener.events) == 1
    assert listener.was_event_received(fixture.aura, event)


def test_event_listener_receives_heal_event(fixture):
    listener = fixture.listener
    event = HealEvent(amount=15.0)

    fixture.aura.process_event(event)

    assert len(listener.events) == 1
    assert listener.was_event_received(fixture.aura, event)


def test_event_listener_receives_add_spell_event(fixture):
    listener = fixture.listener

    fixture.aura.add_spell(fixture.dummy_spell)

    assert len(listener.events) == 1
    event = listener.last_event
    assert isinstance(event, AddSpellEvent)
    assert event.spell is fixture.dummy_spell


def test_event_listener_receives_remove_spell_event(fixture):
    listener = fixture.listener
    fixture.aura.add_spell(fixture.dummy_spell)
    listener.events.clear()

    fixture.aura.remove_spell(fixture.dummy_spell)

    assert len(listener.events) == 1
    event = listener.last_event
    assert isinstance(event, RemoveSpellEvent)
    assert event.spell is fixture.dummy_spell


def test_event_listener_receives_cast_event(fixture):
    listener = fixture.listener

    fixture.aura.cast_spell(fixture.dummy_spell)

    assert len(listener.events) == 1
    event = listener.last_event
    assert isinstance(event, CastEvent)
    assert event.spell is fixture.dummy_spell


def test_multiple_event_listeners(fixture):
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

    listener.events.clear()
    fixture.aura.process_event(DamageEvent(amount=10.0))

    assert len(listener.events) == 0


def test_event_listener_receives_events_in_order(fixture):
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
    initial_magic = fixture.aura.magic.value
    listener = fixture.listener

    fixture.aura.process_event(DamageEvent(amount=10.0))

    aura_from_event = listener.events[0][0]
    assert aura_from_event.magic.value == initial_magic - 10.0


def test_event_listeners_can_be_removed_from_list(fixture):
    listener = MockEventListener()
    fixture.aura.event_listeners.append(listener)

    fixture.aura.event_listeners.remove(listener)

    assert listener not in fixture.aura.event_listeners

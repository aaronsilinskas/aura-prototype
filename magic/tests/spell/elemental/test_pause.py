import pytest

from magic.aura import CastEvent, Spell
from magic.spell.elemental.ignite import IgniteSpell
from magic.spell.elemental.pause import PauseSpell
from magic.spell.elemental.slice import SliceSpell
from magic.tests.helpers import AuraFixture, MockEventListener


class PauseFixture(AuraFixture):
    def __init__(self) -> None:
        super().__init__()
        self.pause_duration = 5.0
        self.pause_spell = PauseSpell(duration=self.pause_duration)
        self.event_listener = MockEventListener()
        self.aura.event_listeners.append(self.event_listener)


@pytest.fixture
def pause_fixture() -> PauseFixture:
    return PauseFixture()


def test_new_pause_spell_has_its_duration_unelapsed_and_is_named_pause():
    pause_spell = PauseSpell(duration=3.0)

    assert pause_spell.duration.length == 3.0
    assert pause_spell.duration.elapsed == 0.0
    assert pause_spell.name == "Pause"


def test_pause_spell_increases_cast_delay(pause_fixture: PauseFixture):
    aura = pause_fixture.aura
    initial_cast_delay = aura.cast_delay.value

    aura.add_spell(pause_fixture.pause_spell)

    assert aura.cast_delay.value > initial_cast_delay


def test_pause_spell_removes_cast_delay_modifier_on_stop(pause_fixture: PauseFixture):
    aura = pause_fixture.aura
    initial_cast_delay = aura.cast_delay.value

    aura.add_spell(pause_fixture.pause_spell)
    assert aura.cast_delay.value > initial_cast_delay

    aura.remove_spell(pause_fixture.pause_spell)

    assert aura.cast_delay.value == initial_cast_delay


def test_pause_spell_expires_after_duration(pause_fixture: PauseFixture):
    aura = pause_fixture.aura

    aura.add_spell(pause_fixture.pause_spell)
    assert pause_fixture.pause_spell in aura.spells

    aura.update(pause_fixture.pause_duration + 1.0)

    assert pause_fixture.pause_spell not in aura.spells


def test_pause_spell_does_not_expire_before_duration(pause_fixture: PauseFixture):
    aura = pause_fixture.aura

    aura.add_spell(pause_fixture.pause_spell)

    aura.update(pause_fixture.pause_duration - 0.5)

    assert pause_fixture.pause_spell in aura.spells


def test_pause_level_scales_duration(pause_fixture: PauseFixture):
    level = 2
    original_duration = pause_fixture.pause_duration
    pause_spell = PauseSpell(duration=original_duration)

    pause_spell.level = level

    expected_duration = Spell.LEVEL_SCALER.scale_value(original_duration, level)
    assert pause_spell.duration.length == expected_duration


def test_pause_spell_prevents_other_spell_casts(pause_fixture: PauseFixture):
    aura = pause_fixture.aura
    damage_spell = SliceSpell(damage=10.0)

    aura.add_spell(pause_fixture.pause_spell)
    pause_fixture.event_listener.events.clear()

    aura.cast_spell(damage_spell)

    assert len(pause_fixture.event_listener.events) == 0


def test_cast_reaches_listeners_when_no_pause_is_active(
    pause_fixture: PauseFixture,
):
    aura = pause_fixture.aura
    new_pause = PauseSpell(duration=3.0)

    aura.cast_spell(new_pause)

    event = pause_fixture.event_listener.last_event
    assert isinstance(event, CastEvent)
    assert event.spell is new_pause


def test_pause_spell_prevents_pause_cast_when_already_paused(
    pause_fixture: PauseFixture,
):
    aura = pause_fixture.aura
    new_pause = PauseSpell(duration=3.0)

    aura.add_spell(pause_fixture.pause_spell)
    pause_fixture.event_listener.events.clear()

    aura.cast_spell(new_pause)

    assert len(pause_fixture.event_listener.events) == 0


def test_pause_spell_does_not_affect_non_cast_events(pause_fixture: PauseFixture):
    from magic.aura import DamageEvent, HealEvent

    aura = pause_fixture.aura
    initial_magic = aura.magic.value

    aura.add_spell(pause_fixture.pause_spell)

    damage_event = DamageEvent(amount=10.0)
    aura.process_event(damage_event)
    assert damage_event.is_canceled is False
    assert aura.magic.value == initial_magic - 10.0

    heal_event = HealEvent(amount=5.0)
    aura.process_event(heal_event)
    assert heal_event.is_canceled is False
    assert aura.magic.value == initial_magic - 5.0


def test_pause_spell_prevents_multiple_spell_types(pause_fixture: PauseFixture):
    aura = pause_fixture.aura

    aura.add_spell(pause_fixture.pause_spell)
    pause_fixture.event_listener.events.clear()

    air_slice = SliceSpell(damage=10.0)
    ignite = IgniteSpell(damage_per_second=5.0, duration=3.0)

    aura.cast_spell(air_slice)
    aura.cast_spell(ignite)

    assert len(pause_fixture.event_listener.events) == 0


def test_pause_spell_cast_delay_modifier_matches_duration(pause_fixture: PauseFixture):
    aura = pause_fixture.aura
    expected_delay = aura.cast_delay.base * pause_fixture.pause_duration

    aura.add_spell(pause_fixture.pause_spell)

    assert aura.cast_delay.value == expected_delay


def test_pause_spell_cast_delay_returns_to_normal_after_expiry(
    pause_fixture: PauseFixture,
):
    aura = pause_fixture.aura
    initial_cast_delay = aura.cast_delay.value

    aura.add_spell(pause_fixture.pause_spell)
    assert aura.cast_delay.value > initial_cast_delay

    aura.update(pause_fixture.pause_duration + 1.0)

    assert aura.cast_delay.value == initial_cast_delay


def test_pause_spell_does_not_add_when_already_paused(pause_fixture: PauseFixture):
    aura = pause_fixture.aura
    new_pause = PauseSpell(duration=3.0)

    aura.add_spell(pause_fixture.pause_spell)
    initial_pause_count = len(aura.spells.get_by_class(PauseSpell))

    cast_event = CastEvent(spell=new_pause)
    aura.process_event(cast_event)

    assert len(aura.spells.get_by_class(PauseSpell)) == initial_pause_count


def test_pause_spell_with_zero_duration_starts_expired():
    pause_spell = PauseSpell(duration=0.0)

    assert pause_spell.duration.length == 0.0
    assert pause_spell.duration.is_expired is True


def test_pause_spell_allows_spell_casts_after_expiry(pause_fixture: PauseFixture):
    aura = pause_fixture.aura
    damage_spell = SliceSpell(damage=10.0)

    aura.add_spell(pause_fixture.pause_spell)

    aura.update(pause_fixture.pause_duration + 1.0)

    cast_event = CastEvent(spell=damage_spell)
    aura.process_event(cast_event)

    assert cast_event.is_canceled is False

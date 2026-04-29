import pytest
from magic.spell.elemental.pause import PauseSpell
from magic.spell.elemental.slice import SliceSpell
from magic.spell.elemental.ignite import IgniteSpell
from magic.aura import CastEvent, Spell
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


def test_pause_spell_initialization():
    """Test that PauseSpell initializes with correct duration."""
    pause_spell = PauseSpell(duration=3.0)

    assert pause_spell.duration.length == 3.0
    assert pause_spell.duration.elapsed == 0.0
    assert pause_spell.name == "Pause"


def test_pause_spell_increases_cast_delay(pause_fixture: PauseFixture):
    """Test that PauseSpell increases the cast delay when started."""
    aura = pause_fixture.aura
    initial_cast_delay = aura.cast_delay.value

    aura.add_spell(pause_fixture.pause_spell)

    # Cast delay should be increased by duration multiplier
    assert aura.cast_delay.value > initial_cast_delay


def test_pause_spell_removes_cast_delay_modifier_on_stop(pause_fixture: PauseFixture):
    """Test that PauseSpell removes cast delay modifier when stopped."""
    aura = pause_fixture.aura
    initial_cast_delay = aura.cast_delay.value

    aura.add_spell(pause_fixture.pause_spell)
    assert aura.cast_delay.value > initial_cast_delay

    aura.remove_spell(pause_fixture.pause_spell)

    assert aura.cast_delay.value == initial_cast_delay


def test_pause_spell_expires_after_duration(pause_fixture: PauseFixture):
    """Test that PauseSpell expires after its duration."""
    aura = pause_fixture.aura

    aura.add_spell(pause_fixture.pause_spell)
    assert pause_fixture.pause_spell in aura.spells

    aura.update(pause_fixture.pause_duration + 1.0)

    assert pause_fixture.pause_spell not in aura.spells


def test_pause_spell_does_not_expire_before_duration(pause_fixture: PauseFixture):
    """Test that PauseSpell does not expire before its duration."""
    aura = pause_fixture.aura

    aura.add_spell(pause_fixture.pause_spell)

    aura.update(pause_fixture.pause_duration - 0.5)

    assert pause_fixture.pause_spell in aura.spells


def test_pause_level(pause_fixture: PauseFixture):
    """Test that PauseSpell level updates duration."""
    aura = pause_fixture.aura
    level = 2
    original_duration = pause_fixture.pause_duration
    pause_spell = PauseSpell(duration=original_duration)

    pause_spell.level = level

    expected_duration = Spell.LEVEL_SCALER.scale_value(original_duration, level)
    assert pause_spell.duration.length == expected_duration


def test_pause_spell_prevents_other_spell_casts(pause_fixture: PauseFixture):
    """Test that PauseSpell prevents casting other spells."""
    aura = pause_fixture.aura
    damage_spell = SliceSpell(damage=10.0)

    # Add the Pause spell to the aura
    aura.add_spell(pause_fixture.pause_spell)
    pause_fixture.event_listener.events.clear()

    # Try to cast a spell while paused
    aura.cast_spell(damage_spell)

    # Cast event should be canceled and never reach listeners
    assert len(pause_fixture.event_listener.events) == 0


def test_pause_spell_cast_not_intercepted_when_no_pause_active(
    pause_fixture: PauseFixture,
):
    """Test that casting when no pause is active doesn't cancel the event."""
    aura = pause_fixture.aura
    new_pause = PauseSpell(duration=3.0)

    # Try to cast a spell when not paused - no pause to intercept it
    aura.cast_spell(new_pause)

    # Event should not be canceled (no pause active to intercept)
    event = pause_fixture.event_listener.last_event
    assert isinstance(event, CastEvent)
    assert event.spell is new_pause


def test_pause_spell_prevents_pause_cast_when_already_paused(
    pause_fixture: PauseFixture,
):
    """Test that PauseSpell prevents casting another pause when already paused."""
    aura = pause_fixture.aura
    new_pause = PauseSpell(duration=3.0)

    aura.add_spell(pause_fixture.pause_spell)
    pause_fixture.event_listener.events.clear()

    # Try to cast another pause while paused
    aura.cast_spell(new_pause)

    # Cast event should be canceled and never reach listeners
    assert len(pause_fixture.event_listener.events) == 0


def test_pause_spell_does_not_affect_non_cast_events(pause_fixture: PauseFixture):
    """Test that PauseSpell does not cancel non-cast events."""
    from magic.aura import DamageEvent, HealEvent

    aura = pause_fixture.aura
    initial_magic = aura.magic.value

    aura.add_spell(pause_fixture.pause_spell)

    # Damage and heal events should still work
    damage_event = DamageEvent(amount=10.0)
    aura.process_event(damage_event)
    assert damage_event.is_canceled is False
    assert aura.magic.value == initial_magic - 10.0

    heal_event = HealEvent(amount=5.0)
    aura.process_event(heal_event)
    assert heal_event.is_canceled is False
    assert aura.magic.value == initial_magic - 5.0


def test_pause_spell_prevents_multiple_spell_types(pause_fixture: PauseFixture):
    """Test that PauseSpell prevents casting different spell types."""
    aura = pause_fixture.aura

    aura.add_spell(pause_fixture.pause_spell)
    pause_fixture.event_listener.events.clear()

    # Try casting different types of spells
    air_slice = SliceSpell(damage=10.0)
    ignite = IgniteSpell(damage_per_second=5.0, duration=3.0)

    aura.cast_spell(air_slice)
    aura.cast_spell(ignite)

    # Both cast events should be canceled
    assert len(pause_fixture.event_listener.events) == 0


def test_pause_spell_cast_delay_modifier_matches_duration(pause_fixture: PauseFixture):
    """Test that the cast delay modifier multiplier matches the pause duration."""
    aura = pause_fixture.aura
    expected_delay = aura.cast_delay.base * pause_fixture.pause_duration

    aura.add_spell(pause_fixture.pause_spell)

    assert aura.cast_delay.value == expected_delay


def test_pause_spell_cast_delay_returns_to_normal_after_expiry(
    pause_fixture: PauseFixture,
):
    """Test that cast delay returns to normal after pause expires."""
    aura = pause_fixture.aura
    initial_cast_delay = aura.cast_delay.value

    aura.add_spell(pause_fixture.pause_spell)
    assert aura.cast_delay.value > initial_cast_delay

    # Wait for pause to expire
    aura.update(pause_fixture.pause_duration + 1.0)

    assert aura.cast_delay.value == initial_cast_delay


def test_pause_spell_does_not_add_when_already_paused(pause_fixture: PauseFixture):
    """Test that casting pause when already paused doesn't add another pause."""
    aura = pause_fixture.aura
    new_pause = PauseSpell(duration=3.0)

    aura.add_spell(pause_fixture.pause_spell)
    initial_pause_count = len(aura.spells.get_by_class(PauseSpell))

    # Try to cast another pause while paused
    cast_event = CastEvent(spell=new_pause)
    aura.process_event(cast_event)

    # No new pause should be added
    assert len(aura.spells.get_by_class(PauseSpell)) == initial_pause_count


def test_pause_spell_zero_duration():
    """Test PauseSpell with zero duration."""
    pause_spell = PauseSpell(duration=0.0)

    assert pause_spell.duration.length == 0.0
    assert pause_spell.duration.is_expired is True


def test_pause_spell_allows_spell_casts_after_expiry(pause_fixture: PauseFixture):
    """Test that spell casts are allowed after pause expires."""
    aura = pause_fixture.aura
    damage_spell = SliceSpell(damage=10.0)

    aura.add_spell(pause_fixture.pause_spell)

    # Wait for pause to expire
    aura.update(pause_fixture.pause_duration + 1.0)

    # Now try to cast a spell
    cast_event = CastEvent(spell=damage_spell)
    aura.process_event(cast_event)

    # Event should not be canceled
    assert cast_event.is_canceled is False

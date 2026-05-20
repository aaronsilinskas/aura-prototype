import pytest

from magic.aura import Spell
from magic.spell.elemental.weight import GRAVITY, AccelerationEvent, WeightSpell
from magic.tests.helpers import AuraFixture


class WeightFixture(AuraFixture):
    def __init__(self) -> None:
        super().__init__()
        self.acceleration_threshold = 1.0  # m/s²
        self.accel_under_threshold_event = AccelerationEvent(
            x_accel=0.0, y_accel=-GRAVITY, z_accel=0.0, remove_gravity=True
        )
        self.accel_above_threshold_event = AccelerationEvent(
            x_accel=6.0, y_accel=0.0, z_accel=-GRAVITY, remove_gravity=True
        )

        self.damage_per_second = 50.0  # damage per second
        self.duration = 10.0  # seconds

        self.weight_spell = WeightSpell(
            acceleration_threshold=self.acceleration_threshold,
            damage_per_second=self.damage_per_second,
            duration=self.duration,
        )


@pytest.fixture
def fixture() -> WeightFixture:
    return WeightFixture()


def test_weight_applies_damage_on_movement(fixture: WeightFixture) -> None:
    aura = fixture.aura
    initial_magic = aura.magic.value

    # Add the weight spell
    aura.add_spell(fixture.weight_spell)

    # Simulate acceleration event above threshold
    aura.process_event(fixture.accel_above_threshold_event)

    # Update the aura for 0.5 seconds
    aura.update(0.5)

    # Check that damage was applied
    assert aura.magic.value == initial_magic - fixture.damage_per_second * 0.5


def test_weight_no_damage_below_threshold(fixture: WeightFixture) -> None:
    aura = fixture.aura
    initial_magic = aura.magic.value

    # Add the weight spell
    aura.add_spell(fixture.weight_spell)

    # Simulate acceleration event above but then below threshold
    aura.process_event(fixture.accel_above_threshold_event)
    aura.process_event(fixture.accel_under_threshold_event)

    # Update the aura for 1 second
    aura.update(1.0)

    # Check that no damage was applied
    assert aura.magic.value == initial_magic


def test_weight_expires_after_duration(fixture: WeightFixture) -> None:
    aura = fixture.aura

    # Add the weight spell
    aura.add_spell(fixture.weight_spell)

    # Simulate acceleration event above threshold
    aura.process_event(fixture.accel_above_threshold_event)

    # Update the aura past the duration of the weight spell
    aura.update(fixture.duration + 1)

    # The weight spell should be expired and removed
    assert fixture.weight_spell not in aura.spells


def test_weight_level(fixture: WeightFixture) -> None:
    level = 3
    original_dps = fixture.damage_per_second

    fixture.weight_spell.level = level

    expected_dps = Spell.LEVEL_SCALER.scale_value(original_dps, level)
    assert fixture.weight_spell.damage_per_second == expected_dps

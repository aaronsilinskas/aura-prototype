import pytest

from magic.aura import DamageEvent, HealEvent, Spell
from magic.spell.elemental.shock import ShockSpell
from magic.tests.helpers import AuraFixture


class ShockFixture(AuraFixture):
    def __init__(self) -> None:
        super().__init__()
        self.aura.magic.value = self.max_magic / 4  # Start at 25% magic
        self.heal_reduction_percentage = 0.5  # 50% reduction in healing
        self.duration = 10.0
        self.shock_spell = ShockSpell(
            heal_reduction_percentage=self.heal_reduction_percentage,
            duration=self.duration,
        )


@pytest.fixture
def fixture() -> ShockFixture:
    return ShockFixture()


def test_shock_reduces_healing(fixture: ShockFixture) -> None:
    aura = fixture.aura
    initial_magic = aura.magic.value
    original_heal_amount = fixture.max_magic / 4  # heal by 25%
    reduced_heal_amount = original_heal_amount * (1 - fixture.heal_reduction_percentage)

    aura.add_spell(fixture.shock_spell)

    aura.process_event(HealEvent(original_heal_amount))

    assert aura.magic.value == initial_magic + reduced_heal_amount


def test_shock_does_not_reduce_damage(fixture: ShockFixture) -> None:
    aura = fixture.aura
    initial_magic = aura.magic.value
    damage_amount = fixture.max_magic / 10  # damage by 10%

    aura.add_spell(fixture.shock_spell)

    aura.process_event(DamageEvent(damage_amount))

    assert aura.magic.value == initial_magic - damage_amount


def test_shock_expires_after_duration(fixture: ShockFixture) -> None:
    aura = fixture.aura

    aura.add_spell(fixture.shock_spell)

    # Update the aura past the duration of the shock spell
    aura.update(fixture.duration + 1)

    # The shock spell should be expired and removed
    assert fixture.shock_spell not in aura.spells


def test_shock_level(fixture: ShockFixture) -> None:
    level = 2
    original_percentage = fixture.heal_reduction_percentage

    fixture.shock_spell.level = level

    expected_percentage = Spell.LEVEL_SCALER.scale_value(original_percentage, level)
    assert fixture.shock_spell.heal_reduction_percentage == expected_percentage

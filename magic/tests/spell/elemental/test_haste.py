import pytest
from magic.aura import Spell
from magic.spell.elemental.haste import HasteSpell
from magic.tests.helpers import AuraFixture


class HasteFixture(AuraFixture):
    def __init__(self) -> None:
        super().__init__()

        self.haste_duration: float = 5.0  # seconds
        self.cast_delay_percentage: float = 0.25  # 25% reduction in cast delay
        self.haste_spell: HasteSpell = HasteSpell(
            duration=self.haste_duration,
            cast_delay_percentage=self.cast_delay_percentage,
        )


@pytest.fixture
def fixture() -> HasteFixture:
    return HasteFixture()


def test_haste_spell_decreases_cast_delay(fixture: HasteFixture) -> None:
    aura = fixture.aura
    original_delay = aura.cast_delay.base

    aura.add_spell(fixture.haste_spell)
    aura.update(1.0)  # Update to apply spell effects

    expected_delay = original_delay * (1 - fixture.cast_delay_percentage)
    assert aura.cast_delay.value == expected_delay


def test_haste_spell_expires_and_restores_cast_delay(fixture: HasteFixture) -> None:
    aura = fixture.aura
    original_delay = aura.cast_delay

    aura.add_spell(fixture.haste_spell)

    # Simulate time passing until the spell expires
    aura.update(fixture.haste_duration + 1.0)

    # cast delay should be restored to original
    assert aura.cast_delay == original_delay


def test_haste_spell_removal_restores_cast_delay(fixture: HasteFixture) -> None:
    aura = fixture.aura
    original_delay = aura.cast_delay

    aura.add_spell(fixture.haste_spell)
    aura.update(1.0)  # Update to apply spell effects

    # Remove the spell before it expires
    aura.remove_spell(fixture.haste_spell)

    # cast delay should be restored to original
    assert aura.cast_delay == original_delay


def test_haste_level(fixture: HasteFixture) -> None:
    level = 3
    original_percentage = fixture.cast_delay_percentage

    fixture.haste_spell.level = level

    expected_percentage = Spell.LEVEL_SCALER.scale_value(original_percentage, level)
    assert fixture.haste_spell.cast_delay_percentage == expected_percentage

import pytest

from magic.aura import Spell
from magic.spell.elemental.flash import FlashSpell
from magic.tests.helpers import AuraFixture


class FlashFixture(AuraFixture):
    def __init__(self) -> None:
        super().__init__()
        self.flash_duration: float = 3.0  # seconds
        self.flash_spell: FlashSpell = FlashSpell(duration=self.flash_duration)


@pytest.fixture
def fixture() -> FlashFixture:
    return FlashFixture()


def test_flash_spell_is_active_during_duration(fixture: FlashFixture) -> None:
    aura = fixture.aura

    aura.add_spell(fixture.flash_spell)
    aura.update(1.0)  # Update partway through duration

    # Flash spell should still be active
    assert fixture.flash_spell in aura.spells


def test_flash_spell_expires_after_duration(fixture: FlashFixture) -> None:
    aura = fixture.aura

    aura.add_spell(fixture.flash_spell)

    # Simulate time passing until the spell expires
    aura.update(fixture.flash_duration + 1.0)

    # The flash spell should be expired and removed
    assert fixture.flash_spell not in aura.spells


def test_flash_level_scales_duration(fixture: FlashFixture) -> None:
    level = 2
    original_duration = fixture.flash_duration

    fixture.flash_spell.level = level

    expected_duration = Spell.LEVEL_SCALER.scale_value(original_duration, level)
    assert fixture.flash_spell.duration.length == expected_duration

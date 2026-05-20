import pytest

from magic.aura import Spell
from magic.spell.elemental.slice import SliceSpell
from magic.tests.helpers import AuraFixture


class SliceFixture(AuraFixture):
    def __init__(self) -> None:
        super().__init__()
        # Deal one-third of max magic as damage
        self.slice_damage: float = self.aura.magic.max.value // 3
        self.slice_spell: SliceSpell = SliceSpell(damage=self.slice_damage)


@pytest.fixture
def slice_fixture() -> SliceFixture:
    return SliceFixture()


def test_slice_instant_damage(slice_fixture: SliceFixture) -> None:
    aura = slice_fixture.aura

    aura.add_spell(slice_fixture.slice_spell)
    aura.update(0.1)  # Any time passing should trigger the instant damage

    assert aura.magic.value == aura.magic.max.value - slice_fixture.slice_damage
    # Spell should be removed after dealing damage
    assert slice_fixture.slice_spell not in aura.spells


def test_slice_multiple_hits(slice_fixture: SliceFixture) -> None:
    aura = slice_fixture.aura

    # Add two slice spells
    slice_spell_1 = SliceSpell(damage=slice_fixture.slice_damage)
    slice_spell_2 = SliceSpell(damage=slice_fixture.slice_damage)

    aura.add_spell(slice_spell_1)
    aura.add_spell(slice_spell_2)
    aura.update(0.1)

    # Both spells should deal damage
    assert aura.magic.value == aura.magic.max.value - (slice_fixture.slice_damage * 2)
    assert len(aura.spells) == 0  # Both spells should be removed


def test_slice_level(slice_fixture: SliceFixture) -> None:
    level = 2
    original_damage = slice_fixture.slice_damage

    slice_fixture.slice_spell.level = level

    expected_damage = Spell.LEVEL_SCALER.scale_value(original_damage, level)
    assert slice_fixture.slice_spell.damage == expected_damage

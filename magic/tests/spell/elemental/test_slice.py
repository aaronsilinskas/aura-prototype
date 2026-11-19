import pytest

from magic.aura import Spell
from magic.spell.elemental.slice import SliceSpell
from magic.tests.helpers import AuraFixture


class SliceFixture(AuraFixture):
    def __init__(self) -> None:
        super().__init__()
        self.slice_damage: float = self.aura.magic.max.value // 3
        self.slice_spell: SliceSpell = SliceSpell(damage=self.slice_damage)


@pytest.fixture
def slice_fixture() -> SliceFixture:
    return SliceFixture()


def test_slice_deals_its_damage_on_the_next_update_then_leaves_the_aura(
    slice_fixture: SliceFixture,
) -> None:
    aura = slice_fixture.aura

    aura.add_spell(slice_fixture.slice_spell)
    aura.update(0.1)

    assert aura.magic.value == aura.magic.max.value - slice_fixture.slice_damage
    assert slice_fixture.slice_spell not in aura.spells


def test_two_slice_spells_each_deal_their_damage(slice_fixture: SliceFixture) -> None:
    aura = slice_fixture.aura

    slice_spell_1 = SliceSpell(damage=slice_fixture.slice_damage)
    slice_spell_2 = SliceSpell(damage=slice_fixture.slice_damage)

    aura.add_spell(slice_spell_1)
    aura.add_spell(slice_spell_2)
    aura.update(0.1)

    assert aura.magic.value == aura.magic.max.value - (slice_fixture.slice_damage * 2)
    assert len(aura.spells) == 0


def test_slice_level_scales_damage(slice_fixture: SliceFixture) -> None:
    level = 2
    original_damage = slice_fixture.slice_damage

    slice_fixture.slice_spell.level = level

    expected_damage = Spell.LEVEL_SCALER.scale_value(original_damage, level)
    assert slice_fixture.slice_spell.damage == expected_damage

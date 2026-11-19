import pytest

from magic.aura import Spell
from magic.spell.elemental.rock import RockSpell
from magic.tests.helpers import AuraFixture


class RockFixture(AuraFixture):
    def __init__(self) -> None:
        super().__init__()
        self.rock_damage: float = self.aura.magic.max.value // 3
        self.rock_spell: RockSpell = RockSpell(damage=self.rock_damage)


@pytest.fixture
def rock_fixture() -> RockFixture:
    return RockFixture()


def test_rock_deals_its_damage_on_the_next_update_then_leaves_the_aura(
    rock_fixture: RockFixture,
) -> None:
    aura = rock_fixture.aura

    aura.add_spell(rock_fixture.rock_spell)
    aura.update(0.1)

    assert aura.magic.value == aura.magic.max.value - rock_fixture.rock_damage
    assert rock_fixture.rock_spell not in aura.spells


def test_two_rock_spells_each_deal_their_damage(rock_fixture: RockFixture) -> None:
    aura = rock_fixture.aura

    rock_spell_1 = RockSpell(damage=rock_fixture.rock_damage)
    rock_spell_2 = RockSpell(damage=rock_fixture.rock_damage)

    aura.add_spell(rock_spell_1)
    aura.add_spell(rock_spell_2)
    aura.update(0.1)

    assert aura.magic.value == aura.magic.max.value - (rock_fixture.rock_damage * 2)
    assert len(aura.spells) == 0


def test_rock_level_scales_damage(rock_fixture: RockFixture) -> None:
    level = 2
    original_damage = rock_fixture.rock_damage

    rock_fixture.rock_spell.level = level

    expected_damage = Spell.LEVEL_SCALER.scale_value(original_damage, level)
    assert rock_fixture.rock_spell.damage == expected_damage

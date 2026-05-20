import pytest

from magic.aura import Spell
from magic.spell.elemental.rock import RockSpell
from magic.tests.helpers import AuraFixture


class RockFixture(AuraFixture):
    def __init__(self) -> None:
        super().__init__()
        # Deal one-third of max magic as damage
        self.rock_damage: float = self.aura.magic.max.value // 3
        self.rock_spell: RockSpell = RockSpell(damage=self.rock_damage)


@pytest.fixture
def rock_fixture() -> RockFixture:
    return RockFixture()


def test_rock_instant_damage(rock_fixture: RockFixture) -> None:
    aura = rock_fixture.aura

    aura.add_spell(rock_fixture.rock_spell)
    aura.update(0.1)  # Any time passing should trigger the instant damage

    assert aura.magic.value == aura.magic.max.value - rock_fixture.rock_damage
    # Spell should be removed after dealing damage
    assert rock_fixture.rock_spell not in aura.spells


def test_rock_multiple_hits(rock_fixture: RockFixture) -> None:
    aura = rock_fixture.aura

    # Add two rock spells
    rock_spell_1 = RockSpell(damage=rock_fixture.rock_damage)
    rock_spell_2 = RockSpell(damage=rock_fixture.rock_damage)

    aura.add_spell(rock_spell_1)
    aura.add_spell(rock_spell_2)
    aura.update(0.1)

    # Both spells should deal damage
    assert aura.magic.value == aura.magic.max.value - (rock_fixture.rock_damage * 2)
    assert len(aura.spells) == 0  # Both spells should be removed


def test_rock_level(rock_fixture: RockFixture) -> None:
    level = 2
    original_damage = rock_fixture.rock_damage

    rock_fixture.rock_spell.level = level

    expected_damage = Spell.LEVEL_SCALER.scale_value(original_damage, level)
    assert rock_fixture.rock_spell.damage == expected_damage

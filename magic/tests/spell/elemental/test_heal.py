import pytest
from magic.aura import Spell
from magic.spell.elemental.heal import HealSpell
from magic.tests.helpers import AuraFixture


class HealFixture(AuraFixture):
    def __init__(self) -> None:
        super().__init__()
        # Start at 1/4 of max magic so we can heal
        self.aura.magic.value = self.aura.magic.max.value // 4
        # Heal one-third of max magic
        self.heal_amount: float = self.aura.magic.max.value // 3
        self.heal_spell: HealSpell = HealSpell(healing=self.heal_amount)


@pytest.fixture
def heal_fixture() -> HealFixture:
    return HealFixture()


def test_heal_instant_healing(heal_fixture: HealFixture) -> None:
    aura = heal_fixture.aura
    initial_magic = aura.magic.value

    aura.add_spell(heal_fixture.heal_spell)
    aura.update(0.1)  # Any time passing should trigger the instant healing

    assert aura.magic.value == initial_magic + heal_fixture.heal_amount
    # Spell should be removed after healing
    assert heal_fixture.heal_spell not in aura.spells


def test_heal_multiple_applications(heal_fixture: HealFixture) -> None:
    aura = heal_fixture.aura
    initial_magic = aura.magic.value

    # Add two heal spells
    heal_spell_1 = HealSpell(healing=heal_fixture.heal_amount)
    heal_spell_2 = HealSpell(healing=heal_fixture.heal_amount)

    aura.add_spell(heal_spell_1)
    aura.add_spell(heal_spell_2)
    aura.update(0.1)

    # Both spells should heal
    assert aura.magic.value == initial_magic + (heal_fixture.heal_amount * 2)
    assert len(aura.spells) == 0  # Both spells should be removed


def test_heal_level(heal_fixture: HealFixture) -> None:
    level = 4
    original_healing = heal_fixture.heal_amount

    heal_fixture.heal_spell.level = level

    expected_healing = Spell.LEVEL_SCALER.scale_value(original_healing, level)
    assert heal_fixture.heal_spell.healing == expected_healing

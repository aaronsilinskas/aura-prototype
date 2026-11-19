import pytest

from magic.aura import DamageEvent, HealEvent, Spell
from magic.spell.elemental.charge import ChargeSpell
from magic.tests.helpers import AuraFixture


class ChargeFixture(AuraFixture):
    def __init__(self) -> None:
        super().__init__()
        self.aura.magic.value = self.max_magic / 4
        self.healing_multiplier = 1.5
        self.duration = 10.0
        self.charge_spell = ChargeSpell(
            healing_multiplier=self.healing_multiplier,
            duration=self.duration,
        )


@pytest.fixture
def fixture() -> ChargeFixture:
    return ChargeFixture()


def test_charge_amplifies_healing(fixture: ChargeFixture) -> None:
    aura = fixture.aura
    initial_magic = aura.magic.value
    original_heal_amount = fixture.max_magic / 4
    charged_heal_amount = original_heal_amount * fixture.healing_multiplier

    aura.add_spell(fixture.charge_spell)

    aura.process_event(HealEvent(original_heal_amount))

    assert aura.magic.value == initial_magic + charged_heal_amount


def test_charge_does_not_amplify_damage(fixture: ChargeFixture) -> None:
    aura = fixture.aura
    initial_magic = aura.magic.value
    damage_amount = fixture.max_magic / 10

    aura.add_spell(fixture.charge_spell)

    aura.process_event(DamageEvent(damage_amount))

    assert aura.magic.value == initial_magic - damage_amount


def test_charge_expires_after_duration(fixture: ChargeFixture) -> None:
    aura = fixture.aura

    aura.add_spell(fixture.charge_spell)
    aura.update(fixture.duration + 1)

    assert fixture.charge_spell not in aura.spells


def test_charge_level_scales_healing_multiplier(fixture: ChargeFixture) -> None:
    level = 2
    original_multiplier = fixture.healing_multiplier

    fixture.charge_spell.level = level

    expected_multiplier = Spell.LEVEL_SCALER.scale_value(original_multiplier, level)
    assert fixture.charge_spell.healing_multiplier == expected_multiplier

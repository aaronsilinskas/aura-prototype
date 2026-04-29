import random

import pytest
from magic.aura import DamageEvent, HealEvent, Spell, SpellTags
from magic.spell.elemental.earth_shield import EarthShieldSpell
from magic.spell.elemental.vulnerable import VulnerableSpell
from magic.tests.helpers import AuraFixture


class VulnerableFixture(AuraFixture):
    def __init__(self) -> None:
        super().__init__()
        self.damage_multiplier = 2.0  # 200% damage taken
        self.duration = round(random.uniform(5.0, 10.0))
        self.vulnerable_spell = VulnerableSpell(
            damage_multiplier=self.damage_multiplier, duration=self.duration
        )
        self.damage_amount = self.max_magic / 4  # damage by 25%


@pytest.fixture
def fixture() -> VulnerableFixture:
    return VulnerableFixture()


def test_vulnerable_removes_existing_shields(fixture: VulnerableFixture) -> None:
    aura = fixture.aura

    # Add shield spells
    shield_spell = EarthShieldSpell(2.0, 3, duration=10)
    shield_spell_2 = EarthShieldSpell(1.5, 2, duration=10)
    aura.add_spell(shield_spell)
    aura.add_spell(shield_spell_2)

    assert aura.spells.get_by_tag(SpellTags.SHIELD) == [shield_spell, shield_spell_2]

    # Add the vulnerable spell
    aura.add_spell(fixture.vulnerable_spell)
    aura.update(0.1)  # Update to trigger shield removal

    # Shield spells should be removed
    assert aura.spells.get_by_tag(SpellTags.SHIELD) == []
    assert list(aura.spells) == [fixture.vulnerable_spell]


def test_vulnerable_removes_shields_while_active(fixture: VulnerableFixture) -> None:
    aura = fixture.aura

    # Add the vulnerable spell
    aura.add_spell(fixture.vulnerable_spell)
    aura.update(0.1)  # Update to ensure spell is active

    # Add shield spells while vulnerable is active
    shield_spell = EarthShieldSpell(2.0, 3, duration=10)
    shield_spell_2 = EarthShieldSpell(1.5, 2, duration=10)
    aura.add_spell(shield_spell)
    aura.add_spell(shield_spell_2)
    aura.update(0.1)  # Update to trigger shield removal

    # Shield spells should be removed
    assert aura.spells.get_by_tag(SpellTags.SHIELD) == []
    assert list(aura.spells) == [fixture.vulnerable_spell]


def test_vulnerable_amplifies_damage_when_no_shields_removed(
    fixture: VulnerableFixture,
) -> None:
    aura = fixture.aura
    initial_magic = aura.magic.value

    vulnerable_damage_amount = fixture.damage_amount * fixture.damage_multiplier

    # No shield spells active
    aura.add_spell(fixture.vulnerable_spell)
    aura.update(0.1)  # Process spell addition

    aura.process_event(DamageEvent(fixture.damage_amount))

    assert aura.magic.value == initial_magic - vulnerable_damage_amount


def test_vulnerable_does_not_amplify_damage_when_shields_removed(
    fixture: VulnerableFixture,
) -> None:
    aura = fixture.aura
    initial_magic = aura.magic.value

    # Shield spell active to be removed
    shield_spell = EarthShieldSpell(reduction=0.5, max_hits=3, duration=10.0)
    aura.add_spell(shield_spell)

    aura.add_spell(fixture.vulnerable_spell)
    aura.update(0.1)  # Process shield removal

    aura.process_event(DamageEvent(fixture.damage_amount))

    assert aura.magic.value == initial_magic - fixture.damage_amount


def test_vulnerable_not_applied_to_healing(fixture: VulnerableFixture) -> None:
    aura = fixture.aura
    heal_amount = aura.magic.max.value / 4  # heal by 25%
    aura.magic.value = fixture.max_magic - heal_amount * 2
    initial_magic = aura.magic.value

    # No shield spells active
    aura.add_spell(fixture.vulnerable_spell)

    aura.process_event(HealEvent(heal_amount))  # Healing event

    assert aura.magic.value == initial_magic + heal_amount


def test_vulnerable_removed_after_expiry(fixture: VulnerableFixture) -> None:
    aura = fixture.aura

    aura.add_spell(fixture.vulnerable_spell)
    aura.update(fixture.duration + 1)

    assert fixture.vulnerable_spell not in aura.spells


def test_vulnerable_level(fixture: VulnerableFixture) -> None:
    level = 2
    original_multiplier = fixture.damage_multiplier

    fixture.vulnerable_spell.level = level

    expected_multiplier = Spell.LEVEL_SCALER.scale_value(original_multiplier, level)
    assert fixture.vulnerable_spell.damage_multiplier == expected_multiplier

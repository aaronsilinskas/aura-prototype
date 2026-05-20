import random

import pytest

from magic.aura import Spell
from magic.spell.elemental.earth_shield import EarthShieldSpell
from magic.spell.elemental.slice import SliceSpell
from magic.tests.helpers import AuraFixture


class EarthShieldFixture(AuraFixture):
    def __init__(self) -> None:
        super().__init__()
        self.damage_reduction = 0.75  # 75% damage reduction
        self.max_hits = random.randint(3, 5)
        self.duration = round(random.uniform(5.0, 10.0))
        self.shield_spell = EarthShieldSpell(
            reduction=self.damage_reduction,
            max_hits=self.max_hits,
            duration=self.duration,
        )
        self.damage = self.aura.magic.max.value / 2  # Damage 1/2 of magic
        self.damage_spell = SliceSpell(damage=self.damage)
        self.damage_after_shield = self.damage * (1 - self.damage_reduction)


@pytest.fixture
def shield_fixture() -> EarthShieldFixture:
    return EarthShieldFixture()


def test_earth_shield_resistance(shield_fixture: EarthShieldFixture) -> None:
    aura = shield_fixture.aura

    aura.add_spell(shield_fixture.shield_spell)
    aura.add_spell(shield_fixture.damage_spell)
    aura.add_spell(shield_fixture.damage_spell)
    aura.update(0.1)  # Trigger damage

    assert aura.magic.value == pytest.approx(
        aura.magic.max.value - (shield_fixture.damage_after_shield * 2)
    )


def test_earth_shield_expiry_by_hits(shield_fixture: EarthShieldFixture) -> None:
    aura = shield_fixture.aura

    aura.add_spell(shield_fixture.shield_spell)

    # Apply damage equal to shield hits
    for _ in range(shield_fixture.max_hits):
        aura.add_spell(shield_fixture.damage_spell)
        aura.update(0.1)  # Trigger damage

    # Final update to process removals because earth spell is processed before damage spell
    aura.update(0.1)

    assert shield_fixture.shield_spell not in aura.spells, (
        "Earth Shield should expire after max_hits"
    )


def test_earth_shield_removed_after_expiry(
    shield_fixture: EarthShieldFixture,
) -> None:
    aura = shield_fixture.aura

    aura.add_spell(shield_fixture.shield_spell)

    # Ellapse time past duration to expire shield
    aura.update(shield_fixture.duration + 1)

    assert shield_fixture.shield_spell not in aura.spells, (
        "Earth Shield should expire after duration"
    )


def test_earth_shield_level(shield_fixture: EarthShieldFixture) -> None:
    level = 2
    original_reduction = shield_fixture.damage_reduction

    shield_fixture.shield_spell.level = level

    # Reduction should be clamped to max 1.0
    expected_reduction = Spell.LEVEL_SCALER.scale_percentage(original_reduction, level)
    assert shield_fixture.shield_spell.reduction == expected_reduction

import random

import pytest

from magic.aura import Spell
from magic.spell.elemental.earth_shield import EarthShieldSpell
from magic.spell.elemental.slice import SliceSpell
from magic.tests.helpers import AuraFixture


class EarthShieldFixture(AuraFixture):
    def __init__(self) -> None:
        super().__init__()
        self.damage_reduction = 0.75
        self.max_hits = random.randint(3, 5)
        self.duration = round(random.uniform(5.0, 10.0))
        self.shield_spell = EarthShieldSpell(
            reduction=self.damage_reduction,
            max_hits=self.max_hits,
            duration=self.duration,
        )
        self.damage = self.aura.magic.max.value / 2
        self.damage_spell = SliceSpell(damage=self.damage)
        self.damage_after_shield = self.damage * (1 - self.damage_reduction)


@pytest.fixture
def shield_fixture() -> EarthShieldFixture:
    return EarthShieldFixture()


def test_earth_shield_reduces_each_hit_by_its_reduction(shield_fixture: EarthShieldFixture) -> None:
    aura = shield_fixture.aura

    aura.add_spell(shield_fixture.shield_spell)
    aura.add_spell(shield_fixture.damage_spell)
    aura.add_spell(shield_fixture.damage_spell)
    aura.update(0.1)

    assert aura.magic.value == pytest.approx(
        aura.magic.max.value - (shield_fixture.damage_after_shield * 2)
    )


def test_earth_shield_expires_after_max_hits(shield_fixture: EarthShieldFixture) -> None:
    aura = shield_fixture.aura

    aura.add_spell(shield_fixture.shield_spell)

    for _ in range(shield_fixture.max_hits):
        aura.add_spell(shield_fixture.damage_spell)
        aura.update(0.1)

    # Final update to process removals because earth spell is processed before damage spell
    aura.update(0.1)

    assert shield_fixture.shield_spell not in aura.spells, (
        "Earth Shield should expire after max_hits"
    )


def test_earth_shield_expires_after_its_duration(
    shield_fixture: EarthShieldFixture,
) -> None:
    aura = shield_fixture.aura

    aura.add_spell(shield_fixture.shield_spell)
    aura.update(shield_fixture.duration + 1)

    assert shield_fixture.shield_spell not in aura.spells, (
        "Earth Shield should expire after duration"
    )


def test_earth_shield_level_scales_reduction(
    shield_fixture: EarthShieldFixture,
) -> None:
    level = 2
    original_reduction = shield_fixture.damage_reduction

    shield_fixture.shield_spell.level = level

    expected_reduction = Spell.LEVEL_SCALER.scale_percentage(original_reduction, level)
    assert shield_fixture.shield_spell.reduction == expected_reduction

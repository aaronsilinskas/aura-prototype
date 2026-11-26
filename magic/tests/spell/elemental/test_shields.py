"""What every damage-reducing shield, Earth Shield and Ice Shield, guarantees."""

import pytest

from magic.aura import Spell
from magic.tests.spell.elemental.shield_fixtures import EarthShieldFixture, IceShieldFixture


@pytest.fixture(params=[EarthShieldFixture, IceShieldFixture], ids=["earth", "ice"])
def shield_fixture(request: pytest.FixtureRequest) -> EarthShieldFixture | IceShieldFixture:
    return request.param()


def test_a_shield_reduces_each_hit_by_its_reduction(shield_fixture) -> None:
    aura = shield_fixture.aura

    aura.add_spell(shield_fixture.shield_spell)
    aura.add_spell(shield_fixture.damage_spell)
    aura.add_spell(shield_fixture.damage_spell)
    aura.update(0.1)

    assert aura.magic.value == pytest.approx(
        aura.magic.max.value - (shield_fixture.damage_after_shield * 2)
    )


def test_a_shield_expires_after_max_hits(shield_fixture) -> None:
    aura = shield_fixture.aura

    aura.add_spell(shield_fixture.shield_spell)

    for _ in range(shield_fixture.max_hits):
        aura.add_spell(shield_fixture.damage_spell)
        aura.update(0.1)

    assert shield_fixture.shield_spell not in aura.spells


def test_a_shield_expires_after_its_duration(shield_fixture) -> None:
    aura = shield_fixture.aura

    aura.add_spell(shield_fixture.shield_spell)
    aura.update(shield_fixture.duration + 1)

    assert shield_fixture.shield_spell not in aura.spells


def test_a_shields_level_scales_its_reduction(shield_fixture) -> None:
    level = 2
    original_reduction = shield_fixture.damage_reduction

    shield_fixture.shield_spell.level = level

    expected_reduction = Spell.LEVEL_SCALER.scale_percentage(original_reduction, level)
    assert shield_fixture.shield_spell.reduction == expected_reduction

import random

import pytest

from magic.aura import Spell
from magic.caster import CastType
from magic.spell.elemental.freeze import FreezeSpell
from magic.spell.elemental.ice_shield import IceShieldSpell
from magic.spell.elemental.slice import SliceSpell
from magic.tests.helpers import AuraFixture, MockCaster


class IceShieldFixture(AuraFixture):
    def __init__(self) -> None:
        super().__init__()
        self.damage_reduction = 0.50  # 50% damage reduction
        self.max_hits = random.randint(3, 5)
        self.duration = round(random.uniform(5.0, 10.0))
        self.caster = MockCaster()
        self.freeze_spell = FreezeSpell(duration=5.0, cast_delay_modifier=2.0)

        self.shield_spell = IceShieldSpell(
            reduction=self.damage_reduction,
            max_hits=self.max_hits,
            duration=self.duration,
            freeze_spell=self.freeze_spell,
            caster=self.caster,
        )

        self.damage = self.aura.magic.max.value / 4  # Damage 1/4 of magic
        self.damage_spell = SliceSpell(damage=self.damage)
        self.damage_after_shield = self.damage * (1 - self.damage_reduction)


@pytest.fixture
def shield_fixture() -> IceShieldFixture:
    return IceShieldFixture()


def test_ice_shield_resistance(shield_fixture: IceShieldFixture) -> None:
    aura = shield_fixture.aura

    aura.add_spell(shield_fixture.shield_spell)
    aura.add_spell(shield_fixture.damage_spell)
    aura.add_spell(shield_fixture.damage_spell)
    aura.update(0.1)  # Trigger damage

    assert aura.magic.value == pytest.approx(
        aura.magic.max.value - (shield_fixture.damage_after_shield * 2)
    )


def test_ice_shield_expiry_by_hits(shield_fixture: IceShieldFixture) -> None:
    aura = shield_fixture.aura

    aura.add_spell(shield_fixture.shield_spell)

    # Apply damage equal to shield hits
    for _ in range(shield_fixture.max_hits):
        aura.add_spell(shield_fixture.damage_spell)
        aura.update(0.1)  # Trigger damage

    # Final update to process removals
    aura.update(0.1)

    assert shield_fixture.shield_spell not in aura.spells, "Ice Shield should expire after max_hits"


def test_ice_shield_removed_after_expiry(
    shield_fixture: IceShieldFixture,
) -> None:
    aura = shield_fixture.aura

    aura.add_spell(shield_fixture.shield_spell)

    # Ellapse time past duration to expire shield
    aura.update(shield_fixture.duration + 1)

    assert shield_fixture.shield_spell not in aura.spells, "Ice Shield should expire after duration"


def test_ice_shield_level(shield_fixture: IceShieldFixture) -> None:
    level = 2
    original_reduction = shield_fixture.damage_reduction

    shield_fixture.shield_spell.level = level

    # Reduction should be clamped to max 1.0
    expected_reduction = Spell.LEVEL_SCALER.scale_percentage(original_reduction, level)
    assert shield_fixture.shield_spell.reduction == expected_reduction


def test_ice_shield_casts_freeze_on_max_hits(shield_fixture: IceShieldFixture) -> None:
    aura = shield_fixture.aura

    aura.add_spell(shield_fixture.shield_spell)

    # Apply damage equal to shield hits
    for _ in range(shield_fixture.max_hits):
        aura.add_spell(shield_fixture.damage_spell)
        aura.update(0.1)  # Trigger damage

    # Final update to process freeze spell
    aura.update(0.1)

    assert shield_fixture.caster.was_cast(shield_fixture.freeze_spell, CastType.AREA_OF_EFFECT), (
        "Ice Shield should cast Freeze spell when max_hits exceeded"
    )


def test_ice_shield_no_freeze_before_max_hits(shield_fixture: IceShieldFixture) -> None:
    aura = shield_fixture.aura

    aura.add_spell(shield_fixture.shield_spell)

    # Apply damage less than shield hits
    for _ in range(shield_fixture.max_hits - 1):
        aura.add_spell(shield_fixture.damage_spell)
        aura.update(0.1)  # Trigger damage

    # Final update to process removals
    aura.update(0.1)

    assert len(shield_fixture.caster.cast_spells) == 0, (
        "Ice Shield should not cast Freeze spell before max_hits exceeded"
    )


def test_ice_shield_no_freeze_after_expiry(shield_fixture: IceShieldFixture) -> None:
    aura = shield_fixture.aura

    aura.add_spell(shield_fixture.shield_spell)

    # Ellapse time past duration to expire shield
    aura.update(shield_fixture.duration + 1)

    # Apply damage equal to shield hits after expiry
    for _ in range(shield_fixture.max_hits):
        aura.add_spell(shield_fixture.damage_spell)
        aura.update(0.1)  # Trigger damage

    assert len(shield_fixture.caster.cast_spells) == 0, (
        "Ice Shield should not cast Freeze spell after expiry"
    )

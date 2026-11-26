import pytest

from magic.caster import CastType
from magic.tests.spell.elemental.shield_fixtures import IceShieldFixture


@pytest.fixture
def shield_fixture() -> IceShieldFixture:
    return IceShieldFixture()


def test_ice_shield_casts_freeze_on_max_hits(shield_fixture: IceShieldFixture) -> None:
    aura = shield_fixture.aura

    aura.add_spell(shield_fixture.shield_spell)

    for _ in range(shield_fixture.max_hits):
        aura.add_spell(shield_fixture.damage_spell)
        aura.update(0.1)

    assert shield_fixture.caster.was_cast(shield_fixture.freeze_spell, CastType.AREA_OF_EFFECT), (
        "Ice Shield should cast Freeze spell when max_hits exceeded"
    )


def test_ice_shield_casts_no_freeze_before_max_hits(shield_fixture: IceShieldFixture) -> None:
    aura = shield_fixture.aura

    aura.add_spell(shield_fixture.shield_spell)

    for _ in range(shield_fixture.max_hits - 1):
        aura.add_spell(shield_fixture.damage_spell)
        aura.update(0.1)

    assert len(shield_fixture.caster.cast_spells) == 0, (
        "Ice Shield should not cast Freeze spell before max_hits exceeded"
    )


def test_ice_shield_casts_no_freeze_after_it_expires(shield_fixture: IceShieldFixture) -> None:
    aura = shield_fixture.aura

    aura.add_spell(shield_fixture.shield_spell)
    aura.update(shield_fixture.duration + 1)

    for _ in range(shield_fixture.max_hits):
        aura.add_spell(shield_fixture.damage_spell)
        aura.update(0.1)

    assert len(shield_fixture.caster.cast_spells) == 0, (
        "Ice Shield should not cast Freeze spell after expiry"
    )

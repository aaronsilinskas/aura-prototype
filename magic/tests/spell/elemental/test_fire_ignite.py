import random

import pytest

from magic.aura import Spell
from magic.spell.elemental.ignite import IgniteSpell
from magic.tests.helpers import AuraFixture


class IgniteFixture(AuraFixture):
    def __init__(self) -> None:
        super().__init__()

        self.ignite_duration: float = round(random.uniform(3.0, 6.0))
        # burn half of max magic over the duration
        self.total_damage = self.aura.magic.max.value / 2
        self.ignite_dps: float = self.total_damage / self.ignite_duration
        self.ignite_spell: IgniteSpell = IgniteSpell(
            damage_per_second=self.ignite_dps, duration=self.ignite_duration
        )


@pytest.fixture
def ignite_fixture() -> IgniteFixture:
    return IgniteFixture()


def test_fire_ignite_full_damage(ignite_fixture: IgniteFixture) -> None:
    aura = ignite_fixture.aura

    aura.add_spell(ignite_fixture.ignite_spell)
    # Simulate time passing beyond duration
    aura.update(ignite_fixture.ignite_duration + 5)

    assert aura.magic.value == pytest.approx(aura.magic.max.value - ignite_fixture.total_damage)
    # Spell should be removed after duration
    assert ignite_fixture.ignite_spell not in aura.spells


def test_fire_ignite_partial_damage(ignite_fixture: IgniteFixture) -> None:
    aura = ignite_fixture.aura
    partial_duration = ignite_fixture.ignite_duration / 2
    partial_damage = ignite_fixture.total_damage * partial_duration / ignite_fixture.ignite_duration

    aura.add_spell(ignite_fixture.ignite_spell)
    # Simulate part of the ignite duration passing
    aura.update(partial_duration)

    # only part of total damage should be applied
    assert aura.magic.value == pytest.approx(aura.magic.max.value - partial_damage)
    # Spell should still be active
    assert ignite_fixture.ignite_spell in aura.spells


def test_fire_ignite_no_damage_after_duration(ignite_fixture: IgniteFixture) -> None:
    aura = ignite_fixture.aura

    aura.add_spell(ignite_fixture.ignite_spell)
    # Simulate time passing beyond duration
    aura.update(ignite_fixture.ignite_duration + 10)

    # All damage applied over duration should be appied, but no more
    assert aura.magic.value == aura.magic.max.value - ignite_fixture.total_damage


def test_fire_ignite_level(ignite_fixture: IgniteFixture) -> None:
    level = 2
    original_dps = ignite_fixture.ignite_dps

    ignite_fixture.ignite_spell.level = level

    expected_dps = Spell.LEVEL_SCALER.scale_value(original_dps, level)
    assert ignite_fixture.ignite_spell.damage_per_second == expected_dps

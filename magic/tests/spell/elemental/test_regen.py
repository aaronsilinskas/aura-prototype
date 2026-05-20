import random

import pytest

from magic.aura import Spell
from magic.spell.elemental.regen import RegenSpell
from magic.tests.helpers import AuraFixture


class RegenFixture(AuraFixture):
    def __init__(self) -> None:
        super().__init__()

        self.regen_duration: float = round(random.uniform(3.0, 6.0))
        # Regenerate half of max magic over the duration
        self.total_regen = self.aura.magic.max.value / 2
        self.regen_rate: float = self.total_regen / self.regen_duration
        self.regen_spell: RegenSpell = RegenSpell(
            regen_rate=self.regen_rate, duration=self.regen_duration
        )


@pytest.fixture
def regen_fixture() -> RegenFixture:
    return RegenFixture()


def test_regen_full_regeneration(regen_fixture: RegenFixture) -> None:
    aura = regen_fixture.aura

    # Start with low magic
    aura.magic.value = 0.0

    aura.add_spell(regen_fixture.regen_spell)
    # Simulate time passing beyond duration
    aura.update(regen_fixture.regen_duration + 5)

    assert aura.magic.value == pytest.approx(regen_fixture.total_regen)
    # Spell should be removed after duration
    assert regen_fixture.regen_spell not in aura.spells


def test_regen_partial_regeneration(regen_fixture: RegenFixture) -> None:
    aura = regen_fixture.aura
    partial_duration = regen_fixture.regen_duration / 2
    partial_regen = regen_fixture.total_regen * partial_duration / regen_fixture.regen_duration

    # Start with low magic
    aura.magic.value = 0.0

    aura.add_spell(regen_fixture.regen_spell)
    # Simulate part of the regen duration passing
    aura.update(partial_duration)

    # Only part of total regen should be applied
    assert aura.magic.value == pytest.approx(partial_regen)
    # Spell should still be active
    assert regen_fixture.regen_spell in aura.spells


def test_regen_caps_at_max_magic(regen_fixture: RegenFixture) -> None:
    aura = regen_fixture.aura

    # Start with magic close to max
    near_max_magic = aura.magic.max.value - (regen_fixture.total_regen / 4)
    aura.magic.value = near_max_magic

    aura.add_spell(regen_fixture.regen_spell)
    # Simulate time passing beyond duration
    aura.update(regen_fixture.regen_duration + 5)

    # Magic should be capped at max
    assert aura.magic.value == pytest.approx(aura.magic.max.value)
    # Spell should be removed after duration
    assert regen_fixture.regen_spell not in aura.spells


def test_regen_damage_during_spell_active(regen_fixture: RegenFixture) -> None:
    aura = regen_fixture.aura

    # Damage halfway through regen duration
    half_of_duration = regen_fixture.regen_duration / 2
    damage_amount = regen_fixture.total_regen  # Damage equal to total regen
    regen_after_damage = regen_fixture.total_regen / 2  # Regen for half of duration
    expected_magic_after_regen = aura.magic.max.value - damage_amount + regen_after_damage

    aura.add_spell(regen_fixture.regen_spell)
    # Simulate time passing for half the duration on max magic
    aura.update(half_of_duration)

    # Apply damage that exceeds current magic
    aura.magic.value -= damage_amount

    # Simulate remaining duration and beyond
    aura.update(regen_fixture.regen_duration + 1.0)

    # Magic should have regenerated correctly after damage
    assert aura.magic.value == pytest.approx(expected_magic_after_regen)
    # Spell should be removed after duration
    assert regen_fixture.regen_spell not in aura.spells


def test_regen_stays_after_max_magic(regen_fixture: RegenFixture) -> None:
    aura = regen_fixture.aura

    # Start with max magic
    aura.magic.value = aura.magic.max.value

    aura.add_spell(regen_fixture.regen_spell)
    # Simulate time passing for half the duration
    aura.update(regen_fixture.regen_duration / 2)

    # Magic should remain at max
    assert aura.magic.value == pytest.approx(aura.magic.max.value)
    # Spell should still be active
    assert regen_fixture.regen_spell in aura.spells


def test_regen_level(regen_fixture: RegenFixture) -> None:
    level = 2
    original_rate = regen_fixture.regen_rate

    regen_fixture.regen_spell.level = level

    expected_rate = Spell.LEVEL_SCALER.scale_value(original_rate, level)
    assert regen_fixture.regen_spell.regen_rate == expected_rate

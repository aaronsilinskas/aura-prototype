import pytest
from magic.spell.combo.combo import SpellCombinations
from magic.spell.combo.combust import CombustCombination
from magic.spell.elemental.ignite import IgniteSpell
from magic.tests.helpers import AuraFixture


class CombustFixture(AuraFixture):
    def __init__(self) -> None:
        super().__init__()
        self.combos = SpellCombinations()
        self.aura.event_listeners.append(self.combos)

        self.combust_combo = CombustCombination()
        self.combos.add(self.combust_combo)

        self.ignite1 = IgniteSpell(damage_per_second=10.0, duration=5.0)
        self.ignite2 = IgniteSpell(damage_per_second=15.0, duration=7.0)
        self.ignite3 = IgniteSpell(damage_per_second=5.0, duration=3.0)


@pytest.fixture
def fixture() -> CombustFixture:
    return CombustFixture()


def test_combust_triggers_with_two_ignites(fixture: CombustFixture):
    aura = fixture.aura
    aura.add_spell(fixture.ignite1)
    aura.add_spell(fixture.ignite2)

    total_dps = fixture.ignite1.damage_per_second + fixture.ignite2.damage_per_second
    duration_max = max(fixture.ignite1.duration.length, fixture.ignite2.duration.length)

    combined_ignites = aura.spells.get_by_class(IgniteSpell)
    assert len(combined_ignites) == 1
    combined_ignite = combined_ignites[0]
    assert combined_ignite.damage_per_second == total_dps
    assert combined_ignite.duration.length == duration_max


def test_combust_does_not_trigger_with_one_ignite(fixture: CombustFixture):
    aura = fixture.aura
    aura.add_spell(fixture.ignite1)

    ignite_spells = aura.spells.get_by_class(IgniteSpell)
    assert len(ignite_spells) == 1
    assert ignite_spells[0] is fixture.ignite1


def test_combust_triggers_only_once_with_three_ignites(fixture: CombustFixture):
    aura = fixture.aura
    aura.add_spell(fixture.ignite1)
    aura.add_spell(fixture.ignite2)
    aura.add_spell(fixture.ignite3)

    total_dps = (
        fixture.ignite1.damage_per_second
        + fixture.ignite2.damage_per_second
        + fixture.ignite3.damage_per_second
    )
    duration_max = max(
        fixture.ignite1.duration.length,
        fixture.ignite2.duration.length,
        fixture.ignite3.duration.length,
    )

    combined_ignites = aura.spells.get_by_class(IgniteSpell)
    assert len(combined_ignites) == 1
    combined_ignite = combined_ignites[0]
    assert combined_ignite.damage_per_second == total_dps
    assert combined_ignite.duration.length == duration_max

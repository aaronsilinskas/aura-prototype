import pytest

from magic.spell.elemental.weaken import WeakenSpell
from magic.tests.helpers import AuraFixture, NoopSpell


class WeakenFixture(AuraFixture):
    def __init__(self) -> None:
        super().__init__()
        self.duration = 5.0
        self.weaken_spell = WeakenSpell(reduction=0.5, duration=self.duration)


@pytest.fixture
def fixture() -> WeakenFixture:
    return WeakenFixture()


def cast_at_level(fixture: WeakenFixture, level: int) -> int:
    """Cast a level-*level* spell from the fixture's aura; return the level it went out at."""
    spell = NoopSpell(tags=[])
    spell.level = level
    fixture.aura.cast_spell(spell)
    return spell.level


def test_weaken_reduces_the_level_of_a_spell_the_aura_casts(fixture: WeakenFixture) -> None:
    fixture.aura.add_spell(fixture.weaken_spell)

    assert cast_at_level(fixture, 4) == 2


def test_a_weakened_cast_never_drops_below_level_one(fixture: WeakenFixture) -> None:
    fixture.aura.add_spell(WeakenSpell(reduction=1.0, duration=fixture.duration))

    assert cast_at_level(fixture, 4) == 1


def test_a_negative_weaken_reduction_never_raises_a_cast_level(fixture: WeakenFixture) -> None:
    fixture.aura.add_spell(WeakenSpell(reduction=-0.5, duration=fixture.duration))

    assert cast_at_level(fixture, 4) == 4


def test_weaken_stops_reducing_cast_levels_once_its_duration_has_passed(
    fixture: WeakenFixture,
) -> None:
    fixture.aura.add_spell(fixture.weaken_spell)

    for _ in range(3):
        fixture.aura.update(fixture.duration)

    assert cast_at_level(fixture, 4) == 4


def test_weaken_level_raises_its_reduction(fixture: WeakenFixture) -> None:
    fixture.weaken_spell.level = 3
    fixture.aura.add_spell(fixture.weaken_spell)

    assert cast_at_level(fixture, 10) == 4

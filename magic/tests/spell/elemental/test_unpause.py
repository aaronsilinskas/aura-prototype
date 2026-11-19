import pytest

from magic.spell.elemental.ignite import IgniteSpell
from magic.spell.elemental.pause import PauseSpell
from magic.spell.elemental.unpause import UnpauseSpell
from magic.tests.helpers import AuraFixture


class UnpauseFixture(AuraFixture):
    def __init__(self) -> None:
        super().__init__()
        self.unpause_spell = UnpauseSpell()


@pytest.fixture
def fixture() -> UnpauseFixture:
    return UnpauseFixture()


def test_unpause_spell_removes_all_pauses(fixture: UnpauseFixture) -> None:
    aura = fixture.aura
    pause_spell_1 = PauseSpell(duration=10.0)
    pause_spell_2 = PauseSpell(duration=5.0)

    aura.add_spell(pause_spell_1)
    aura.add_spell(pause_spell_2)
    assert pause_spell_1 in aura.spells
    assert pause_spell_2 in aura.spells

    aura.add_spell(fixture.unpause_spell)
    aura.update(0.1)

    assert pause_spell_1 not in aura.spells
    assert pause_spell_2 not in aura.spells


def test_unpause_spell_no_pause_present(fixture: UnpauseFixture) -> None:
    aura = fixture.aura

    assert all(not isinstance(spell, PauseSpell) for spell in aura.spells)

    aura.add_spell(fixture.unpause_spell)
    aura.update(0.1)

    assert all(not isinstance(spell, PauseSpell) for spell in aura.spells)


def test_unpause_spell_with_other_spells(fixture: UnpauseFixture) -> None:
    aura = fixture.aura
    pause_spell = PauseSpell(duration=10.0)
    other_spell = IgniteSpell(damage_per_second=5.0, duration=10.0)

    aura.add_spell(pause_spell)
    aura.add_spell(other_spell)
    assert pause_spell in aura.spells
    assert other_spell in aura.spells

    aura.add_spell(fixture.unpause_spell)
    aura.update(0.1)

    assert pause_spell not in aura.spells
    assert other_spell in aura.spells


def test_unpause_level(fixture: UnpauseFixture) -> None:
    fixture.unpause_spell.level = 2

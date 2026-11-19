import pytest

from magic.aura import AddSpellEvent, Aura, RemoveSpellEvent
from magic.spell.combo.combo import SpellCombination, SpellCombinations
from magic.spell.elemental.ignite import IgniteSpell
from magic.tests.helpers import AuraFixture


@pytest.fixture
def fixture() -> AuraFixture:
    return AuraFixture()


class MockSpellCombination(SpellCombination):
    def __init__(self):
        self.check_called = False
        self.last_aura = None
        self.should_return = False

    def check(self, aura: Aura) -> bool:
        self.check_called = True
        self.last_aura = aura
        return self.should_return


def test_an_added_combination_is_held_by_the_manager():
    combinations = SpellCombinations()
    mock_combo = MockSpellCombination()

    combinations.add(mock_combo)

    assert len(combinations) == 1
    assert list(combinations) == [mock_combo]


def test_the_manager_holds_every_added_combination():
    combinations = SpellCombinations()
    combo1 = MockSpellCombination()
    combo2 = MockSpellCombination()
    combo3 = MockSpellCombination()

    combinations.add(combo1)
    combinations.add(combo2)
    combinations.add(combo3)

    assert len(combinations) == 3
    assert combo1 in combinations
    assert combo2 in combinations
    assert combo3 in combinations


def test_a_removed_combination_is_no_longer_held():
    combinations = SpellCombinations()
    mock_combo = MockSpellCombination()

    combinations.add(mock_combo)
    assert len(combinations) == 1

    combinations.remove(mock_combo)

    assert len(combinations) == 0
    assert mock_combo not in combinations


def test_removing_a_combination_the_manager_does_not_hold_is_a_no_op():
    combinations = SpellCombinations()

    combinations.remove(MockSpellCombination())

    assert len(combinations) == 0


def test_removing_one_combination_keeps_the_others():
    combinations = SpellCombinations()
    combo1 = MockSpellCombination()
    combo2 = MockSpellCombination()
    combo3 = MockSpellCombination()

    combinations.add(combo1)
    combinations.add(combo2)
    combinations.add(combo3)

    combinations.remove(combo2)

    assert len(combinations) == 2
    assert combo1 in combinations
    assert combo2 not in combinations
    assert combo3 in combinations


def test_a_new_combination_manager_holds_no_combinations():
    combinations = SpellCombinations()

    assert len(combinations) == 0


def test_a_new_combination_manager_iterates_nothing():
    combinations = SpellCombinations()

    result = list(combinations)

    assert result == []


def test_an_added_spell_event_checks_a_combination_against_the_aura(fixture: AuraFixture):
    aura = fixture.aura

    combinations = SpellCombinations()
    mock_combo = MockSpellCombination()
    combinations.add(mock_combo)

    spell = IgniteSpell(damage_per_second=10.0, duration=5.0)
    event = AddSpellEvent(spell)

    combinations.on_spell_event(aura, event)

    assert mock_combo.check_called
    assert mock_combo.last_aura is aura


def test_a_removed_spell_event_checks_no_combination(fixture: AuraFixture):
    combinations = SpellCombinations()
    mock_combo = MockSpellCombination()
    combinations.add(mock_combo)

    spell = IgniteSpell(damage_per_second=10.0, duration=5.0)
    event = RemoveSpellEvent(spell)

    combinations.on_spell_event(fixture.aura, event)

    assert not mock_combo.check_called


def test_an_added_spell_event_checks_every_combination(fixture: AuraFixture):
    combinations = SpellCombinations()

    combo1 = MockSpellCombination()
    combo2 = MockSpellCombination()
    combo3 = MockSpellCombination()

    combinations.add(combo1)
    combinations.add(combo2)
    combinations.add(combo3)

    spell = IgniteSpell(damage_per_second=10.0, duration=5.0)
    event = AddSpellEvent(spell)

    combinations.on_spell_event(fixture.aura, event)

    assert combo1.check_called
    assert combo2.check_called
    assert combo3.check_called


def test_an_added_spell_event_with_no_combinations_does_not_raise(fixture: AuraFixture):
    combinations = SpellCombinations()
    spell = IgniteSpell(damage_per_second=10.0, duration=5.0)
    event = AddSpellEvent(spell)

    combinations.on_spell_event(fixture.aura, event)


def test_combinations_listening_on_an_aura_check_it_when_a_spell_is_added(
    fixture: AuraFixture,
):
    aura = fixture.aura

    combinations = SpellCombinations()
    mock_combo = MockSpellCombination()
    combinations.add(mock_combo)
    aura.event_listeners.append(combinations)
    spell = IgniteSpell(damage_per_second=10.0, duration=5.0)

    aura.add_spell(spell)

    assert mock_combo.check_called
    assert mock_combo.last_aura is fixture.aura

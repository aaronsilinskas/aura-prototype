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


def test_add_combination():
    combinations = SpellCombinations()
    mock_combo = MockSpellCombination()

    combinations.add(mock_combo)

    assert len(combinations) == 1
    assert list(combinations) == [mock_combo]


def test_add_multiple_combinations():
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


def test_remove_combination():
    combinations = SpellCombinations()
    mock_combo = MockSpellCombination()

    combinations.add(mock_combo)
    assert len(combinations) == 1

    combinations.remove(mock_combo)
    assert len(combinations) == 0
    assert mock_combo not in combinations


def test_remove_nonexistent_combination():
    combinations = SpellCombinations()

    combinations.remove(MockSpellCombination())

    assert len(combinations) == 0


def test_remove_one_of_multiple():
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


def test_len_empty():
    combinations = SpellCombinations()
    assert len(combinations) == 0


def test_iter_empty():
    combinations = SpellCombinations()
    result = list(combinations)
    assert result == []


def test_on_spell_event_with_add_spell_event(fixture: AuraFixture):
    aura = fixture.aura

    combinations = SpellCombinations()
    mock_combo = MockSpellCombination()
    combinations.add(mock_combo)

    spell = IgniteSpell(damage_per_second=10.0, duration=5.0)
    event = AddSpellEvent(spell)

    combinations.on_spell_event(aura, event)

    assert mock_combo.check_called
    assert mock_combo.last_aura is aura


def test_on_spell_event_with_non_add_spell_event(fixture: AuraFixture):
    combinations = SpellCombinations()
    mock_combo = MockSpellCombination()
    combinations.add(mock_combo)

    spell = IgniteSpell(damage_per_second=10.0, duration=5.0)
    event = RemoveSpellEvent(spell)

    combinations.on_spell_event(fixture.aura, event)

    assert not mock_combo.check_called


def test_on_spell_event_calls_all_combinations(fixture: AuraFixture):
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


def test_on_spell_event_with_no_combinations(fixture: AuraFixture):
    combinations = SpellCombinations()
    spell = IgniteSpell(damage_per_second=10.0, duration=5.0)
    event = AddSpellEvent(spell)

    combinations.on_spell_event(fixture.aura, event)


def test_as_event_listener_integration(fixture: AuraFixture):
    aura = fixture.aura

    combinations = SpellCombinations()
    mock_combo = MockSpellCombination()
    combinations.add(mock_combo)

    aura.event_listeners.append(combinations)

    spell = IgniteSpell(damage_per_second=10.0, duration=5.0)
    aura.add_spell(spell)

    assert mock_combo.check_called
    assert mock_combo.last_aura is fixture.aura

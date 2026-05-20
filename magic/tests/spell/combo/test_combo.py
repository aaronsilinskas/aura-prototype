import pytest

from magic.aura import AddSpellEvent, Aura, RemoveSpellEvent
from magic.spell.combo.combo import SpellCombination, SpellCombinations
from magic.spell.elemental.ignite import IgniteSpell
from magic.tests.helpers import AuraFixture


@pytest.fixture
def fixture() -> AuraFixture:
    return AuraFixture()


class MockSpellCombination(SpellCombination):
    """Mock implementation of SpellCombination for testing."""

    def __init__(self):
        self.check_called = False
        self.last_aura = None
        self.should_return = False

    def check(self, aura: Aura) -> bool:
        self.check_called = True
        self.last_aura = aura
        return self.should_return


def test_add_combination():
    """Test adding a spell combination to the manager."""
    combinations = SpellCombinations()
    mock_combo = MockSpellCombination()

    combinations.add(mock_combo)

    assert len(combinations) == 1
    assert list(combinations) == [mock_combo]


def test_add_multiple_combinations():
    """Test adding multiple spell combinations."""
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
    """Test removing a spell combination from the manager."""
    combinations = SpellCombinations()
    mock_combo = MockSpellCombination()

    combinations.add(mock_combo)
    assert len(combinations) == 1

    combinations.remove(mock_combo)
    assert len(combinations) == 0
    assert mock_combo not in combinations


def test_remove_nonexistent_combination():
    """Test removing a combination that is not in the manager."""
    combinations = SpellCombinations()

    # Should not raise an error
    combinations.remove(MockSpellCombination())

    assert len(combinations) == 0


def test_remove_one_of_multiple():
    """Test removing one combination when multiple are present."""
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
    """Test __len__ returns 0 for empty combinations."""
    combinations = SpellCombinations()
    assert len(combinations) == 0


def test_iter_empty():
    """Test iterating over empty combinations."""
    combinations = SpellCombinations()
    result = list(combinations)
    assert result == []


def test_on_spell_event_with_add_spell_event(fixture: AuraFixture):
    """Test that on_spell_event calls check on AddSpellEvent."""
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
    """Test that on_spell_event does not call check on non-AddSpellEvent."""
    combinations = SpellCombinations()
    mock_combo = MockSpellCombination()
    combinations.add(mock_combo)

    spell = IgniteSpell(damage_per_second=10.0, duration=5.0)
    event = RemoveSpellEvent(spell)

    combinations.on_spell_event(fixture.aura, event)

    assert not mock_combo.check_called


def test_on_spell_event_calls_all_combinations(fixture: AuraFixture):
    """Test that on_spell_event calls check on all registered combinations."""
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
    """Test that on_spell_event handles empty combinations list."""
    combinations = SpellCombinations()
    spell = IgniteSpell(damage_per_second=10.0, duration=5.0)
    event = AddSpellEvent(spell)

    # Should not raise an error
    combinations.on_spell_event(fixture.aura, event)


def test_as_event_listener_integration(fixture: AuraFixture):
    """Test SpellCombinations as an event listener on an Aura."""
    aura = fixture.aura

    combinations = SpellCombinations()
    mock_combo = MockSpellCombination()
    combinations.add(mock_combo)

    # Register as event listener
    aura.event_listeners.append(combinations)

    # Add a spell, which should trigger the combination check
    spell = IgniteSpell(damage_per_second=10.0, duration=5.0)
    aura.add_spell(spell)

    assert mock_combo.check_called
    assert mock_combo.last_aura is fixture.aura

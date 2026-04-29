from unittest.mock import Mock
import pytest
from pytest_mock import MockerFixture
from magic.values import ValueModifier, ValueModifiers


@pytest.fixture
def mock_callback(mocker: MockerFixture) -> Mock:
    """Fixture to provide a mock callback for tests."""
    return mocker.Mock()


def test_modify_no_modifiers(mock_callback):
    """Test that modify returns the base value when no modifiers are present."""
    mgr = ValueModifiers(mock_callback)

    assert mgr.modify(10.0) == 10.0


def test_modify_single_modifier(mock_callback):
    """Test that modify applies a single multiplier."""
    mgr = ValueModifiers(mock_callback)
    modifier = ValueModifier(2.5, 1.0)

    mgr.add(modifier)

    assert mgr.modify(4.0) == 10.0


def test_modify_multiplemodifiers(mock_callback):
    """Test that modify applies multiple multipliers sequentially."""
    mgr = ValueModifiers(mock_callback)
    modifier1 = ValueModifier(2.0, 1.0)
    modifier2 = ValueModifier(0.25, 1.0)

    mgr.add(modifier1)
    mgr.add(modifier2)

    assert mgr.modify(10.0) == 5.0


def test_add(mock_callback):
    """Test that adding a modifier shows in the modifiers list."""
    mgr = ValueModifiers(mock_callback)
    modifier = ValueModifier(1.0, 1.0)

    mgr.add(modifier)

    assert list(mgr) == [modifier]


def test_add_triggers_callback(mock_callback):
    """Test that adding a modifier triggers the provided callback."""
    mgr = ValueModifiers(mock_callback)

    mgr.add(ValueModifier(1.0, 1.0))

    mock_callback.assert_called_once()


def test_add_duplicate_modifier(mock_callback):
    """Test that adding a duplicate modifier does not add it again."""
    mgr = ValueModifiers(mock_callback)
    modifier = ValueModifier(1.0, 1.0)

    added_first_time = mgr.add(modifier)
    added_second_time = mgr.add(modifier)

    assert added_first_time is True
    assert added_second_time is False
    assert len(mgr) == 1


def test_remove(mock_callback):
    """Test that removing a modifier removes it from the modifiers list."""
    mgr = ValueModifiers(mock_callback)
    modifier = ValueModifier(1.0, 1.0)

    mgr.add(modifier)
    mgr.remove(modifier)

    assert len(mgr) == 0


def test_remove_triggers_callback(mock_callback):
    """Test that removing a modifier triggers the provided callback."""
    mgr = ValueModifiers(mock_callback)
    modifier = ValueModifier(1.0, 1.0)

    mgr.add(modifier)
    mgr.remove(modifier)

    # once for add, once for remove
    assert mock_callback.call_count == 2


def test_remove_nonexistent_modifier(mock_callback):
    """Test that removing a nonexistent modifier does not raise an error."""
    mgr = ValueModifiers(mock_callback)
    modifier = ValueModifier(1.0, 1.0)

    mgr.remove(modifier)


def test_update_no_expiry(mock_callback):
    """Test that update does not remove modifiers or trigger callback if none expire."""
    mgr = ValueModifiers(mock_callback)
    modifier = ValueModifier(1.0, 1.0)

    mgr.add(modifier)
    mgr.update(0.5)

    assert list(mgr) == [modifier]
    assert mock_callback.call_count == 1  # only called on add


def test_update_expiry(mock_callback):
    """Test that update removes expired modifiers and triggers callback."""
    mgr = ValueModifiers(mock_callback)
    modifier = ValueModifier(1.0, 0.1)  # Expires after 0.1 seconds

    mgr.add(modifier)
    mgr.update(0.2)

    assert len(mgr) == 0
    # once for add, once for removal
    assert mock_callback.call_count == 2


def test_update_multiple_expiry(mock_callback):
    """Test that update removes multiple expired modifiers."""
    mgr = ValueModifiers(mock_callback)
    modifier1 = ValueModifier(1.0, 0.1)
    modifier2 = ValueModifier(1.0, 0.2)

    mgr.add(modifier1)
    mgr.add(modifier2)
    mgr.update(0.3)

    assert len(mgr) == 0
    # once for each add, then only once no matter how many were removed
    assert mock_callback.call_count == 3


def test_update_mixed_expiry(mock_callback):
    """Test that update removes only expired modifiers."""
    mgr = ValueModifiers(mock_callback)
    modifier1 = ValueModifier(1.0, 0.1)  # Expires
    modifier2 = ValueModifier(1.0, 1.0)  # Does not expire

    mgr.add(modifier1)
    mgr.add(modifier2)
    mgr.update(0.2)

    assert list(mgr) == [modifier2]
    # once for each add, then once for removal
    assert mock_callback.call_count == 3


def test_no_callback_provided():
    """Test that ValueModifiers works without a callback."""
    mgr = ValueModifiers()

    modifier = ValueModifier(1.0, 0.1)
    mgr.add(modifier)
    mgr.update(0.2)

    assert len(mgr) == 0

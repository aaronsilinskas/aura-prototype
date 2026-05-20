from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

from magic.values import ValueModifier, ValueWithModifiers


@pytest.fixture
def mock_callback(mocker: MockerFixture) -> Mock:
    """Fixture to provide a mock callback for tests."""
    return mocker.Mock()


def test_initialization_default():
    """Test initialization with default values."""
    val = ValueWithModifiers()

    assert val.base == 0.0
    assert val.value == 0.0
    assert len(val.modifiers) == 0


def test_initialization_with_base_value():
    """Test initialization with a custom base value."""
    val = ValueWithModifiers(base_value=42.0)

    assert val.base == 42.0
    assert val.value == 42.0


def test_initialization_with_callback(mock_callback):
    """Test that initialization with a callback doesn't trigger it."""
    ValueWithModifiers(base_value=10.0, value_changed=mock_callback)

    mock_callback.assert_not_called()


def test_base_setter_updates_value():
    """Test that setting base value updates the modified value."""
    val = ValueWithModifiers(base_value=10.0)

    val.base = 20.0

    assert val.base == 20.0
    assert val.value == 20.0


def test_base_setter_triggers_callback(mock_callback):
    """Test that setting base value triggers the callback."""
    val = ValueWithModifiers(base_value=10.0, value_changed=mock_callback)

    val.base = 20.0

    mock_callback.assert_called_once()


def test_value_with_single_modifier():
    """Test that value is correctly modified with a single modifier."""
    val = ValueWithModifiers(base_value=10.0)
    modifier = ValueModifier(multiplier=2.0, duration=1.0)

    val.modifiers.add(modifier)

    assert val.value == 20.0


def test_value_with_multiple_modifiers():
    """Test that value is correctly modified with multiple modifiers."""
    val = ValueWithModifiers(base_value=10.0)
    modifier1 = ValueModifier(multiplier=2.0, duration=1.0)
    modifier2 = ValueModifier(multiplier=1.5, duration=1.0)

    val.modifiers.add(modifier1)
    val.modifiers.add(modifier2)

    assert val.value == 30.0  # 10 * 2 * 1.5


def test_adding_modifier_triggers_callback(mock_callback):
    """Test that adding a modifier triggers the value_changed callback."""
    val = ValueWithModifiers(base_value=10.0, value_changed=mock_callback)
    modifier = ValueModifier(multiplier=2.0, duration=1.0)

    val.modifiers.add(modifier)

    mock_callback.assert_called_once()


def test_removing_modifier_triggers_callback(mock_callback):
    """Test that removing a modifier triggers the value_changed callback."""
    val = ValueWithModifiers(base_value=10.0, value_changed=mock_callback)
    modifier = ValueModifier(multiplier=2.0, duration=1.0)

    val.modifiers.add(modifier)
    mock_callback.reset_mock()

    val.modifiers.remove(modifier)

    mock_callback.assert_called_once()


def test_removing_modifier_updates_value():
    """Test that removing a modifier updates the value correctly."""
    val = ValueWithModifiers(base_value=10.0)
    modifier = ValueModifier(multiplier=2.0, duration=1.0)

    val.modifiers.add(modifier)
    assert val.value == 20.0

    val.modifiers.remove(modifier)
    assert val.value == 10.0


def test_update_with_no_expiring_modifiers():
    """Test that update with non-expiring modifiers doesn't change value."""
    val = ValueWithModifiers(base_value=10.0)
    modifier = ValueModifier(multiplier=2.0, duration=1.0)

    val.modifiers.add(modifier)
    initial_value = val.value

    val.update(0.5)

    assert val.value == initial_value


def test_update_with_expiring_modifier(mock_callback):
    """Test that update removes expired modifiers and triggers callback."""
    val = ValueWithModifiers(base_value=10.0, value_changed=mock_callback)
    modifier = ValueModifier(multiplier=2.0, duration=1.0)

    val.modifiers.add(modifier)
    mock_callback.reset_mock()

    val.update(1.5)  # Expire the modifier

    assert val.value == 10.0  # Back to base
    mock_callback.assert_called_once()


def test_update_propagates_to_modifiers():
    """Test that update properly propagates elapsed time to modifiers."""
    val = ValueWithModifiers(base_value=10.0)
    modifier = ValueModifier(multiplier=2.0, duration=1.0)

    val.modifiers.add(modifier)
    val.update(0.5)

    # Modifier should still be active
    assert len(val.modifiers) == 1

    val.update(0.6)  # Total elapsed: 1.1

    # Modifier should now be expired
    assert len(val.modifiers) == 0


def test_base_change_with_active_modifiers():
    """Test that changing base value recalculates with active modifiers."""
    val = ValueWithModifiers(base_value=10.0)
    modifier = ValueModifier(multiplier=2.0, duration=1.0)

    val.modifiers.add(modifier)
    assert val.value == 20.0

    val.base = 15.0

    assert val.value == 30.0  # 15 * 2


def test_zero_base_value_with_modifiers():
    """Test that modifiers work correctly with a zero base value."""
    val = ValueWithModifiers(base_value=0.0)
    modifier = ValueModifier(multiplier=5.0, duration=1.0)

    val.modifiers.add(modifier)

    assert val.value == 0.0  # 0 * 5 = 0


def test_negative_base_value():
    """Test that negative base values work correctly."""
    val = ValueWithModifiers(base_value=-10.0)
    modifier = ValueModifier(multiplier=2.0, duration=1.0)

    val.modifiers.add(modifier)

    assert val.value == -20.0


def test_modifier_with_fractional_multiplier():
    """Test modifiers with fractional multipliers."""
    val = ValueWithModifiers(base_value=10.0)
    modifier = ValueModifier(multiplier=0.5, duration=1.0)

    val.modifiers.add(modifier)

    assert val.value == 5.0


def test_multiple_updates_with_expiring_modifiers(mock_callback):
    """Test multiple updates where modifiers expire at different times."""
    val = ValueWithModifiers(base_value=10.0, value_changed=mock_callback)
    modifier1 = ValueModifier(multiplier=2.0, duration=1.0)
    modifier2 = ValueModifier(multiplier=1.5, duration=2.0)

    val.modifiers.add(modifier1)
    val.modifiers.add(modifier2)
    mock_callback.reset_mock()

    assert val.value == 30.0  # 10 * 2 * 1.5

    val.update(1.5)  # modifier1 expires

    assert val.value == 15.0  # 10 * 1.5
    assert mock_callback.call_count == 1

    val.update(1.0)  # modifier2 expires

    assert val.value == 10.0
    assert mock_callback.call_count == 2


def test_callback_none_doesnt_error():
    """Test that operations work correctly when no callback is provided."""
    val = ValueWithModifiers(base_value=10.0, value_changed=None)
    modifier = ValueModifier(multiplier=2.0, duration=0.5)

    val.modifiers.add(modifier)
    val.base = 20.0
    val.update(1.0)

    # Should not raise any errors
    assert val.value == 20.0

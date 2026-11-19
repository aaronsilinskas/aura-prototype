from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

from magic.values import ValueModifier, ValueWithModifiers


@pytest.fixture
def mock_callback(mocker: MockerFixture) -> Mock:
    return mocker.Mock()


def test_a_default_value_starts_at_zero_with_no_modifiers():
    val = ValueWithModifiers()

    assert val.base == 0.0
    assert val.value == 0.0
    assert len(val.modifiers) == 0


def test_a_value_starts_at_its_base_value():
    val = ValueWithModifiers(base_value=42.0)

    assert val.base == 42.0
    assert val.value == 42.0


def test_constructing_a_value_does_not_call_its_callback(mock_callback):
    ValueWithModifiers(base_value=10.0, value_changed=mock_callback)

    mock_callback.assert_not_called()


def test_setting_the_base_updates_the_value():
    val = ValueWithModifiers(base_value=10.0)

    val.base = 20.0

    assert val.base == 20.0
    assert val.value == 20.0


def test_setting_the_base_calls_the_callback(mock_callback):
    val = ValueWithModifiers(base_value=10.0, value_changed=mock_callback)

    val.base = 20.0

    mock_callback.assert_called_once()


def test_value_applies_a_single_modifier():
    val = ValueWithModifiers(base_value=10.0)
    modifier = ValueModifier(multiplier=2.0, duration=1.0)

    val.modifiers.add(modifier)

    assert val.value == 20.0


def test_value_applies_every_modifier():
    val = ValueWithModifiers(base_value=10.0)
    modifier1 = ValueModifier(multiplier=2.0, duration=1.0)
    modifier2 = ValueModifier(multiplier=1.5, duration=1.0)

    val.modifiers.add(modifier1)
    val.modifiers.add(modifier2)

    assert val.value == 30.0  # 10 * 2 * 1.5


def test_adding_a_modifier_calls_the_callback(mock_callback):
    val = ValueWithModifiers(base_value=10.0, value_changed=mock_callback)
    modifier = ValueModifier(multiplier=2.0, duration=1.0)

    val.modifiers.add(modifier)

    mock_callback.assert_called_once()


def test_removing_a_modifier_calls_the_callback(mock_callback):
    val = ValueWithModifiers(base_value=10.0, value_changed=mock_callback)
    modifier = ValueModifier(multiplier=2.0, duration=1.0)

    val.modifiers.add(modifier)
    mock_callback.reset_mock()

    val.modifiers.remove(modifier)

    mock_callback.assert_called_once()


def test_removing_a_modifier_restores_the_base_value():
    val = ValueWithModifiers(base_value=10.0)
    modifier = ValueModifier(multiplier=2.0, duration=1.0)

    val.modifiers.add(modifier)
    assert val.value == 20.0

    val.modifiers.remove(modifier)
    assert val.value == 10.0


def test_update_before_a_modifier_expires_keeps_the_value():
    val = ValueWithModifiers(base_value=10.0)
    modifier = ValueModifier(multiplier=2.0, duration=1.0)

    val.modifiers.add(modifier)
    initial_value = val.value

    val.update(0.5)

    assert val.value == initial_value


def test_update_drops_an_expired_modifier_and_calls_the_callback(mock_callback):
    val = ValueWithModifiers(base_value=10.0, value_changed=mock_callback)
    modifier = ValueModifier(multiplier=2.0, duration=1.0)

    val.modifiers.add(modifier)
    mock_callback.reset_mock()

    val.update(1.5)

    assert val.value == 10.0
    mock_callback.assert_called_once()


def test_update_expires_a_modifier_once_its_duration_has_elapsed():
    val = ValueWithModifiers(base_value=10.0)
    modifier = ValueModifier(multiplier=2.0, duration=1.0)

    val.modifiers.add(modifier)
    val.update(0.5)

    assert len(val.modifiers) == 1

    val.update(0.6)  # Total elapsed: 1.1

    assert len(val.modifiers) == 0


def test_changing_the_base_reapplies_active_modifiers():
    val = ValueWithModifiers(base_value=10.0)
    modifier = ValueModifier(multiplier=2.0, duration=1.0)

    val.modifiers.add(modifier)
    assert val.value == 20.0

    val.base = 15.0

    assert val.value == 30.0  # 15 * 2


def test_modifiers_leave_a_zero_base_at_zero():
    val = ValueWithModifiers(base_value=0.0)
    modifier = ValueModifier(multiplier=5.0, duration=1.0)

    val.modifiers.add(modifier)

    assert val.value == 0.0  # 0 * 5 = 0


def test_modifiers_scale_a_negative_base():
    val = ValueWithModifiers(base_value=-10.0)
    modifier = ValueModifier(multiplier=2.0, duration=1.0)

    val.modifiers.add(modifier)

    assert val.value == -20.0


def test_a_fractional_multiplier_reduces_the_value():
    val = ValueWithModifiers(base_value=10.0)
    modifier = ValueModifier(multiplier=0.5, duration=1.0)

    val.modifiers.add(modifier)

    assert val.value == 5.0


def test_modifiers_expiring_at_different_times_each_drop_out_in_turn(mock_callback):
    val = ValueWithModifiers(base_value=10.0, value_changed=mock_callback)
    modifier1 = ValueModifier(multiplier=2.0, duration=1.0)
    modifier2 = ValueModifier(multiplier=1.5, duration=2.0)

    val.modifiers.add(modifier1)
    val.modifiers.add(modifier2)
    mock_callback.reset_mock()

    assert val.value == 30.0  # 10 * 2 * 1.5

    val.update(1.5)

    assert val.value == 15.0  # 10 * 1.5
    assert mock_callback.call_count == 1

    val.update(1.0)

    assert val.value == 10.0
    assert mock_callback.call_count == 2


def test_a_value_without_a_callback_supports_every_operation():
    val = ValueWithModifiers(base_value=10.0, value_changed=None)
    modifier = ValueModifier(multiplier=2.0, duration=0.5)

    val.modifiers.add(modifier)
    val.base = 20.0
    val.update(1.0)

    assert val.value == 20.0

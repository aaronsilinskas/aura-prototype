from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

from magic.values import ValueModifier, ValueModifiers


@pytest.fixture
def mock_callback(mocker: MockerFixture) -> Mock:
    return mocker.Mock()


def test_modify_returns_the_base_value_with_no_modifiers(mock_callback):
    mgr = ValueModifiers(mock_callback)

    assert mgr.modify(10.0) == 10.0


def test_modify_applies_a_single_multiplier(mock_callback):
    mgr = ValueModifiers(mock_callback)
    modifier = ValueModifier(2.5, 1.0)

    mgr.add(modifier)

    assert mgr.modify(4.0) == 10.0


def test_modify_applies_every_multiplier_in_turn(mock_callback):
    mgr = ValueModifiers(mock_callback)
    modifier1 = ValueModifier(2.0, 1.0)
    modifier2 = ValueModifier(0.25, 1.0)

    mgr.add(modifier1)
    mgr.add(modifier2)

    assert mgr.modify(10.0) == 5.0


def test_an_added_modifier_is_listed(mock_callback):
    mgr = ValueModifiers(mock_callback)
    modifier = ValueModifier(1.0, 1.0)

    mgr.add(modifier)

    assert list(mgr) == [modifier]


def test_adding_a_modifier_calls_the_callback(mock_callback):
    mgr = ValueModifiers(mock_callback)

    mgr.add(ValueModifier(1.0, 1.0))

    mock_callback.assert_called_once()


def test_adding_a_modifier_twice_keeps_one_copy(mock_callback):
    mgr = ValueModifiers(mock_callback)
    modifier = ValueModifier(1.0, 1.0)

    added_first_time = mgr.add(modifier)
    added_second_time = mgr.add(modifier)

    assert added_first_time is True
    assert added_second_time is False
    assert len(mgr) == 1


def test_a_removed_modifier_is_no_longer_listed(mock_callback):
    mgr = ValueModifiers(mock_callback)
    modifier = ValueModifier(1.0, 1.0)

    mgr.add(modifier)
    mgr.remove(modifier)

    assert len(mgr) == 0


def test_removing_a_modifier_calls_the_callback(mock_callback):
    mgr = ValueModifiers(mock_callback)
    modifier = ValueModifier(1.0, 1.0)

    mgr.add(modifier)
    mgr.remove(modifier)

    # once for add, once for remove
    assert mock_callback.call_count == 2


def test_removing_an_unlisted_modifier_does_not_raise(mock_callback):
    mgr = ValueModifiers(mock_callback)
    modifier = ValueModifier(1.0, 1.0)

    mgr.remove(modifier)


def test_update_keeps_unexpired_modifiers_without_calling_the_callback(mock_callback):
    mgr = ValueModifiers(mock_callback)
    modifier = ValueModifier(1.0, 1.0)

    mgr.add(modifier)
    mgr.update(0.5)

    assert list(mgr) == [modifier]
    assert mock_callback.call_count == 1  # only called on add


def test_update_removes_an_expired_modifier_and_calls_the_callback(mock_callback):
    mgr = ValueModifiers(mock_callback)
    modifier = ValueModifier(1.0, 0.1)

    mgr.add(modifier)
    mgr.update(0.2)

    assert len(mgr) == 0
    # once for add, once for removal
    assert mock_callback.call_count == 2


def test_update_removes_every_expired_modifier_with_one_callback(mock_callback):
    mgr = ValueModifiers(mock_callback)
    modifier1 = ValueModifier(1.0, 0.1)
    modifier2 = ValueModifier(1.0, 0.2)

    mgr.add(modifier1)
    mgr.add(modifier2)
    mgr.update(0.3)

    assert len(mgr) == 0
    # once for each add, then only once no matter how many were removed
    assert mock_callback.call_count == 3


def test_update_removes_only_expired_modifiers(mock_callback):
    mgr = ValueModifiers(mock_callback)
    expiring = ValueModifier(1.0, 0.1)
    lasting = ValueModifier(1.0, 1.0)

    mgr.add(expiring)
    mgr.add(lasting)
    mgr.update(0.2)

    assert list(mgr) == [lasting]
    # once for each add, then once for removal
    assert mock_callback.call_count == 3


def test_modifiers_without_a_callback_still_expire():
    mgr = ValueModifiers()

    modifier = ValueModifier(1.0, 0.1)
    mgr.add(modifier)
    mgr.update(0.2)

    assert len(mgr) == 0

import pytest

from magic.values import Duration


def test_initialization():
    duration = Duration(length=10.0)
    assert duration.length == 10.0
    assert duration.elapsed == 0.0
    assert duration.remaining == 10.0
    assert duration.is_expired is False


def test_update_partial():
    duration = Duration(length=10.0)
    is_expired = duration.update(3.0)

    assert duration.elapsed == 3.0
    assert duration.remaining == 7.0
    assert is_expired is False
    assert duration.is_expired is False


def test_update_multiple_times():
    duration = Duration(length=10.0)
    duration.update(3.0)
    duration.update(2.0)
    duration.update(1.0)

    assert duration.elapsed == 6.0
    assert duration.remaining == 4.0
    assert duration.is_expired is False


def test_update_to_expiration():
    duration = Duration(length=10.0)
    is_expired = duration.update(10.0)

    assert duration.elapsed == 10.0
    assert duration.remaining == 0.0
    assert is_expired is True
    assert duration.is_expired is True


def test_update_beyond_expiration():
    duration = Duration(length=10.0)
    is_expired = duration.update(15.0)

    assert duration.elapsed == 15.0
    assert duration.remaining == 0.0  # Should not go negative
    assert is_expired is True
    assert duration.is_expired is True


def test_reset():
    duration = Duration(length=10.0)
    duration.update(5.0)

    assert duration.elapsed == 5.0
    assert duration.remaining == 5.0

    duration.reset()

    assert duration.elapsed == 0.0
    assert duration.remaining == 10.0
    assert duration.is_expired is False


def test_zero_length_duration():
    duration = Duration(length=0.0)

    assert duration.length == 0.0
    assert duration.is_expired is True  # Already expired


def test_zero_length_duration_after_update():
    duration = Duration(length=0.0)
    is_expired = duration.update(1.0)

    assert is_expired is True
    assert duration.elapsed == 1.0
    assert duration.remaining == 0.0


def test_small_increments():
    duration = Duration(length=1.0)

    # Update 9 times with 0.1, then once more to exceed
    for _ in range(9):
        is_expired = duration.update(0.1)
        assert is_expired is False

    # Final update should push it over the edge
    is_expired = duration.update(0.2)

    assert duration.elapsed == pytest.approx(1.1)
    assert duration.remaining == 0.0
    assert is_expired is True
    assert duration.is_expired is True


def test_exact_expiration_boundary():
    duration = Duration(length=5.0)
    duration.update(4.99)
    assert duration.is_expired is False

    duration.update(0.01)
    assert duration.elapsed == pytest.approx(5.0)
    assert duration.is_expired is True


def test_length_setter():
    duration = Duration(length=10.0)
    assert duration.length == 10.0

    duration.length = 20.0
    assert duration.length == 20.0
    assert duration.remaining == 20.0


def test_length_setter_changes_remaining():
    duration = Duration(length=10.0)
    duration.update(5.0)
    assert duration.elapsed == 5.0
    assert duration.remaining == 5.0

    # Increase length
    duration.length = 15.0
    assert duration.remaining == 10.0
    assert duration.is_expired is False


def test_length_setter_can_cause_expiration():
    duration = Duration(length=10.0)
    duration.update(5.0)
    assert duration.is_expired is False

    # Decrease length below elapsed time
    duration.length = 3.0
    assert duration.remaining == 0.0
    assert duration.is_expired is True


def test_length_setter_negative_remaining():
    duration = Duration(length=10.0)
    duration.update(8.0)

    # Set length to less than elapsed
    duration.length = 5.0
    assert duration.remaining == 0.0  # Should not be negative
    assert duration.is_expired is True

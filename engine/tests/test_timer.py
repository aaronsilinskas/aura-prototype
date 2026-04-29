from unittest.mock import patch

import pytest

from engine.timer import Timer


def _timer_with_mock_time(start: float = 0.0):
    with patch("engine.timer.time.monotonic", return_value=start):
        timer = Timer()
    return timer


def test_elapsed_is_zero_before_first_update():
    timer = _timer_with_mock_time()

    assert timer.elapsed == 0.0


def test_total_is_zero_before_first_update():
    timer = _timer_with_mock_time()

    assert timer.total == 0.0


def test_elapsed_reflects_time_since_last_update():
    timer = _timer_with_mock_time(start=1.0)

    with patch("engine.timer.time.monotonic", return_value=1.25):
        timer.update()

    assert timer.elapsed == pytest.approx(0.25)


def test_total_reflects_time_since_construction_after_one_update():
    timer = _timer_with_mock_time(start=10.0)

    with patch("engine.timer.time.monotonic", return_value=10.1):
        timer.update()

    assert timer.total == pytest.approx(0.1)


def test_elapsed_reflects_only_most_recent_delta():
    timer = _timer_with_mock_time(start=0.0)

    with patch("engine.timer.time.monotonic", return_value=0.5):
        timer.update()

    with patch("engine.timer.time.monotonic", return_value=0.75):
        timer.update()

    assert timer.elapsed == pytest.approx(0.25)


def test_total_accumulates_across_multiple_updates():
    timer = _timer_with_mock_time(start=0.0)

    with patch("engine.timer.time.monotonic", return_value=0.1):
        timer.update()
    with patch("engine.timer.time.monotonic", return_value=0.25):
        timer.update()
    with patch("engine.timer.time.monotonic", return_value=0.30):
        timer.update()

    assert timer.total == pytest.approx(0.30)


def test_elapsed_is_zero_when_no_time_passes_between_updates():
    timer = _timer_with_mock_time(start=5.0)

    with patch("engine.timer.time.monotonic", return_value=5.0):
        timer.update()

    assert timer.elapsed == pytest.approx(0.0)


def test_elapsed_captures_full_size_of_spike():
    timer = _timer_with_mock_time(start=0.0)

    with patch("engine.timer.time.monotonic", return_value=10.0):
        timer.update()

    assert timer.elapsed == pytest.approx(10.0)


def test_total_includes_full_size_of_spike():
    timer = _timer_with_mock_time(start=0.0)

    with patch("engine.timer.time.monotonic", return_value=10.0):
        timer.update()

    assert timer.total == pytest.approx(10.0)

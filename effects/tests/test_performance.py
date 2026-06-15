import pytest

from effects.performance import PerformanceTracker


def test_frame_time_peak_tracks_the_slowest_frame_seen_so_far(monkeypatch) -> None:
    tracker = PerformanceTracker(log_interval=100.0)

    times = iter([0.0, 0.010, 0.035])
    monkeypatch.setattr("effects.performance.time.monotonic", lambda: next(times))

    tracker.start_frame()
    tracker.complete_frame(0.010)

    tracker.start_frame()
    tracker.complete_frame(0.035)

    tracker.start_frame()
    tracker.complete_frame(0.040)

    assert tracker.frame_time_peak == pytest.approx(0.025)


def test_frame_time_peak_is_zero_before_any_frame_completes() -> None:
    tracker = PerformanceTracker(log_interval=100.0)

    assert tracker.frame_time_peak == 0.0

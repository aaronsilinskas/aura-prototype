import pytest

from effects.performance import PerformanceTracker


def test_frame_time_peak_tracks_the_slowest_frame_seen_so_far(monkeypatch) -> None:
    # complete_frame samples time.monotonic itself, so each frame consumes two
    # ticks (start_frame + complete_frame); the first tick is the constructor.
    # Frame durations: 0.010, 0.025 (peak), 0.005.
    times = iter([0.0, 0.0, 0.010, 0.010, 0.035, 0.035, 0.040])
    monkeypatch.setattr("effects.performance.time.monotonic", lambda: next(times))

    tracker = PerformanceTracker(log_interval=100.0)

    tracker.start_frame()
    tracker.complete_frame()

    tracker.start_frame()
    tracker.complete_frame()

    tracker.start_frame()
    tracker.complete_frame()

    assert tracker.frame_time_peak == pytest.approx(0.025)


def test_frame_time_peak_is_zero_before_any_frame_completes() -> None:
    tracker = PerformanceTracker(log_interval=100.0)

    assert tracker.frame_time_peak == 0.0


def test_complete_frame_signals_when_a_log_interval_elapses(monkeypatch) -> None:
    # ctor, then (start_frame, complete_frame) per frame. log_interval is 0.05:
    # frame 1 ends at 0.02 (past the initial gate at 0.0), frame 2 at 0.04
    # (still inside the 0.07 window), frame 3 at 0.08 (past it again).
    times = iter([0.0, 0.01, 0.02, 0.03, 0.04, 0.07, 0.08])
    monkeypatch.setattr("effects.performance.time.monotonic", lambda: next(times))

    tracker = PerformanceTracker(log_interval=0.05)

    tracker.start_frame()
    assert tracker.complete_frame() is True

    tracker.start_frame()
    assert tracker.complete_frame() is False

    tracker.start_frame()
    assert tracker.complete_frame() is True

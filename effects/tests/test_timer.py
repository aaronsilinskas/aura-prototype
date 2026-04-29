import pytest

from effects.effect import EffectTimer

# ---------------------------------------------------------------------------
# Elapsed tracking
# ---------------------------------------------------------------------------


def test_timer_exposes_last_frame_delta_after_update() -> None:
    timer = EffectTimer()

    timer.update(0.032)

    assert timer.elapsed == pytest.approx(0.032)


def test_timer_total_accumulates_across_multiple_frames() -> None:
    timer = EffectTimer()

    timer.update(0.016)
    timer.update(0.016)
    timer.update(0.016)

    assert timer.total == pytest.approx(0.048)


def test_timer_elapsed_reflects_only_the_most_recent_frame() -> None:
    timer = EffectTimer()
    timer.update(0.1)

    timer.update(0.025)

    assert timer.elapsed == pytest.approx(0.025)


# ---------------------------------------------------------------------------
# Progress — with duration
# ---------------------------------------------------------------------------


def test_timer_progress_starts_at_zero_before_any_updates() -> None:
    timer = EffectTimer(duration=1.0)

    assert timer.progress == 0.0


def test_timer_progress_reaches_one_exactly_when_total_equals_duration() -> None:
    timer = EffectTimer(duration=0.5)

    timer.update(0.5)

    assert timer.progress == pytest.approx(1.0)


def test_timer_progress_is_proportional_to_elapsed_fraction_of_duration() -> None:
    timer = EffectTimer(duration=2.0)

    timer.update(1.0)

    assert timer.progress == pytest.approx(0.5)


def test_timer_progress_does_not_exceed_one_when_total_overshoots_duration() -> None:
    timer = EffectTimer(duration=0.1)

    timer.update(1.0)

    assert timer.progress == pytest.approx(1.0)


def test_timer_signals_complete_when_total_reaches_duration() -> None:
    timer = EffectTimer(duration=0.5)

    done = timer.update(0.5)

    assert done is True


def test_timer_does_not_signal_complete_before_duration_is_reached() -> None:
    timer = EffectTimer(duration=1.0)

    done = timer.update(0.5)

    assert done is False


# ---------------------------------------------------------------------------
# Progress — without duration
# ---------------------------------------------------------------------------


def test_timer_without_duration_never_signals_complete() -> None:
    timer = EffectTimer()

    done = timer.update(9999.0)

    assert done is False


def test_timer_without_duration_keeps_progress_at_zero_regardless_of_elapsed() -> None:
    timer = EffectTimer()

    timer.update(10.0)

    assert timer.progress == 0.0


# ---------------------------------------------------------------------------
# Zero-delta and edge inputs
# ---------------------------------------------------------------------------


def test_timer_zero_delta_frame_does_not_change_total_or_progress() -> None:
    timer = EffectTimer(duration=1.0)
    timer.update(0.5)

    timer.update(0.0)

    assert timer.total == pytest.approx(0.5)
    assert timer.progress == pytest.approx(0.5)

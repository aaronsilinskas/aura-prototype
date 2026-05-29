import pytest

from effects.render import EffectTimer

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
# Zero-delta and edge inputs
# ---------------------------------------------------------------------------


def test_timer_zero_delta_frame_does_not_change_total() -> None:
    timer = EffectTimer()
    timer.update(0.5)

    timer.update(0.0)

    assert timer.total == pytest.approx(0.5)

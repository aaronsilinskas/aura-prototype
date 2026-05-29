import pytest

from effects.layers.scroll import PhaseScroll, ScrollOffset

# ---------------------------------------------------------------------------
# ScrollOffset — position shift
# ---------------------------------------------------------------------------


def test_scroll_offset_apply_returns_same_position_before_first_update() -> None:
    scroll = ScrollOffset(speed=1.0)

    assert scroll.apply(0.5) == 0.5


def test_scroll_offset_apply_shifts_position_by_speed_times_elapsed() -> None:
    scroll = ScrollOffset(speed=1.0)
    scroll.update(0.25)

    assert scroll.apply(0.0) == pytest.approx(0.25)


def test_scroll_offset_wraps_position_past_one() -> None:
    scroll = ScrollOffset(speed=1.0)
    scroll.update(0.5)

    # 0.8 + 0.5 = 1.3 → wraps to 0.3
    assert scroll.apply(0.8) == pytest.approx(0.3)


def test_scroll_offset_accumulates_offset_across_multiple_updates() -> None:
    scroll = ScrollOffset(speed=1.0)
    scroll.update(0.1)
    scroll.update(0.1)
    scroll.update(0.1)

    # total offset = 0.3
    assert scroll.apply(0.0) == pytest.approx(0.3)


def test_scroll_offset_offset_wraps_when_it_exceeds_one() -> None:
    scroll = ScrollOffset(speed=1.0)
    scroll.update(1.5)  # offset = 1.5 % 1.0 = 0.5

    assert scroll.apply(0.0) == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# PhaseScroll — returned position is always in [0.0, 1.0)
# ---------------------------------------------------------------------------


def test_phase_scroll_apply_returns_value_in_unit_range_before_update() -> None:
    scroll = PhaseScroll(speed=0.5, min_phase=0.1, max_phase=0.2)

    result = scroll.apply(0.5)

    assert 0.0 <= result < 1.0


def test_phase_scroll_apply_returns_value_in_unit_range_after_updates() -> None:
    scroll = PhaseScroll(speed=0.5, min_phase=0.05, max_phase=0.1)
    for _ in range(20):
        scroll.update(0.016)

    for pos in [0.0, 0.25, 0.5, 0.75]:
        result = scroll.apply(pos)
        assert 0.0 <= result < 1.0, f"apply({pos}) = {result} out of range"

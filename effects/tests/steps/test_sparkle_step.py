import pytest

from effects.effect import Effect, EffectState
from effects.steps.sparkle import sparkle
from effects.tests.helpers import make_timer


def test_sparkle_with_zero_count_does_not_change_output_value() -> None:
    effect = Effect("test", lambda _: 0.5).add_steps([sparkle(sparkle_count=0)])
    state = EffectState()

    effect.update(state, make_timer(0.1))

    for pos in [0.0, 0.25, 0.5, 0.75]:
        assert effect.value(state, pos, 1) == pytest.approx(0.5)


def test_sparkle_output_does_not_decrease_below_input_value() -> None:
    # Sparkles add non-negative intensity; output can only increase.
    effect = Effect("test", lambda _: 0.4).add_steps([sparkle(sparkle_count=4)])
    state = EffectState()

    effect.update(state, make_timer(0.1))

    for pos in [0.0, 0.25, 0.5, 0.75]:
        assert effect.value(state, pos, 4) >= 0.4


def test_sparkle_brightens_positions_above_base_value_at_peak_intensity() -> None:
    # With a non-zero base, sparkles add on top — they don't replace the base.
    # At peak intensity the sparkle position should exceed the base value.
    effect = Effect("test", lambda _: 0.4).add_steps(
        [
            sparkle(
                sparkle_count=1,
                spawn_delay_rate=0.0,
                fade_in_rate=100.0,
            )
        ]
    )
    state = EffectState()

    effect.update(state, make_timer(0.0))  # idle → fade_in (intensity still 0)
    effect.update(state, make_timer(1.0))  # fade_in raises intensity to 1.0

    max_value = max(effect.value(state, i / 10, 10) for i in range(10))
    assert max_value > 0.4


def test_sparkle_returns_to_base_value_after_full_fade_in_and_fade_out_cycle() -> None:
    # After a complete idle → fade_in → fade_out → idle cycle, the sparkle
    # has fully disappeared and every position returns to the base value.
    effect = Effect("test", lambda _: 0.0).add_steps(
        [
            sparkle(
                sparkle_count=1,
                spawn_delay_rate=0.0,
                fade_in_rate=100.0,
                fade_out_rate=100.0,
            )
        ]
    )
    state = EffectState()

    effect.update(state, make_timer(0.0))  # idle → fade_in
    effect.update(state, make_timer(1.0))  # fade_in → 1.0 → fade_out
    effect.update(state, make_timer(1.0))  # fade_out → 0.0 → idle

    max_value = max(effect.value(state, i / 10, 10) for i in range(10))
    assert max_value == pytest.approx(0.0)


def test_sparkle_adds_positive_value_immediately_when_spawn_delay_is_zero() -> None:
    # spawn_delay_rate=0 causes all sparkles to spawn on the first frame
    # and begin fading in on the second.
    effect = Effect("test", lambda _: 0.0).add_steps(
        [
            sparkle(
                sparkle_count=1,
                spawn_delay_rate=0.0,
                fade_in_rate=100.0,
            )
        ]
    )
    state = EffectState()

    effect.update(state, make_timer(0.0))  # frame 0: idle → fade_in (intensity still 0)
    effect.update(state, make_timer(1.0))  # frame 1: fade_in raises intensity to 1.0

    # Sample at fine resolution to guarantee we hit the spawned sparkle's pixel.
    has_sparkle = any(effect.value(state, i / 10, 10) > 0.0 for i in range(10))
    assert has_sparkle


def test_sparkle_stays_dark_while_spawn_delay_has_not_elapsed() -> None:
    # With a large spawn delay the sparkle stays in PHASE_IDLE for the first
    # frame; no contribution should appear in the output.
    effect = Effect("test", lambda _: 0.0).add_steps(
        [
            sparkle(
                sparkle_count=1,
                spawn_delay_rate=100.0,  # very long delay
                fade_in_rate=100.0,
            )
        ]
    )
    state = EffectState()

    effect.update(state, make_timer(0.01))  # tiny elapsed — delay not yet expired

    has_sparkle = any(effect.value(state, i / 10, 10) > 0.0 for i in range(10))
    assert not has_sparkle


def test_sparkle_contribution_decreases_with_distance_from_sparkle_position() -> None:
    # A sparkle at a known float position should contribute its full intensity
    # exactly at that position and progressively less toward one pixel away,
    # with zero contribution beyond one pixel.
    #
    # Strategy: use a large pixel_count so we can place the sparkle precisely
    # at pixel 50 (slot_pos=0.5, pixel_count=100) and sample at known offsets.
    import unittest.mock

    pixel_count = 100
    sparkle_pos = 0.5  # maps to pixel 50

    effect = Effect("test", lambda _: 0.0).add_steps(
        [
            sparkle(
                sparkle_count=1,
                spawn_delay_rate=0.0,
                fade_in_rate=100.0,
            )
        ]
    )
    state = EffectState()

    # Seed the random position deterministically.
    with unittest.mock.patch("effects.steps.sparkle.random.random", return_value=sparkle_pos):
        effect.update(state, make_timer(0.0))  # idle → fade_in, slot_pos set
    effect.update(state, make_timer(1.0))  # fade_in → intensity 1.0

    at_center = effect.value(state, sparkle_pos, pixel_count)  # dist=0 → full
    at_half = effect.value(state, 50.5 / pixel_count, pixel_count)  # dist=0.5 → 0.5
    at_edge = effect.value(state, 51.0 / pixel_count, pixel_count)  # dist=1.0 → 0
    beyond = effect.value(state, 52.0 / pixel_count, pixel_count)  # dist=2.0 → 0

    assert at_center == pytest.approx(1.0)
    assert at_half == pytest.approx(0.5)
    assert at_edge == pytest.approx(0.0)
    assert beyond == pytest.approx(0.0)


def test_sparkle_respawns_and_becomes_visible_again_after_completing_a_full_cycle() -> None:
    # After idle → fade_in → fade_out → idle, the spawn_delay is reset and
    # the sparkle should become visible again on a subsequent frame.
    effect = Effect("test", lambda _: 0.0).add_steps(
        [
            sparkle(
                sparkle_count=1,
                spawn_delay_rate=0.0,
                fade_in_rate=100.0,
                fade_out_rate=100.0,
            )
        ]
    )
    state = EffectState()

    effect.update(state, make_timer(0.0))  # idle → fade_in
    effect.update(state, make_timer(1.0))  # fade_in → fade_out
    effect.update(state, make_timer(1.0))  # fade_out → idle
    effect.update(state, make_timer(0.0))  # idle → fade_in (re-spawn)
    effect.update(state, make_timer(1.0))  # fade_in → intensity 1.0

    has_sparkle = any(effect.value(state, i / 10, 10) > 0.0 for i in range(10))
    assert has_sparkle


def test_sparkle_multiple_sparkles_can_be_simultaneously_active() -> None:
    # With no spawn delay and fast fade-in, all sparkle_count sparkles reach
    # peak intensity on the second frame. Sampling at fine pixel resolution
    # should find at least sparkle_count lit positions.
    sparkle_count = 4
    pixel_count = 100
    effect = Effect("test", lambda _: 0.0).add_steps(
        [
            sparkle(
                sparkle_count=sparkle_count,
                spawn_delay_rate=0.0,
                fade_in_rate=100.0,
            )
        ]
    )
    state = EffectState()

    effect.update(state, make_timer(0.0))  # idle → fade_in
    effect.update(state, make_timer(1.0))  # fade_in raises all to 1.0

    lit_count = sum(
        1 for i in range(pixel_count) if effect.value(state, i / pixel_count, pixel_count) > 0.0
    )
    assert lit_count >= sparkle_count

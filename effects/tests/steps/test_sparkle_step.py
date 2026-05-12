import pytest

from effects.effect import Effect, EffectState
from effects.steps.sparkle import sparkle
from effects.tests.helpers import make_timer


def test_sparkle_with_zero_count_does_not_change_output_value() -> None:
    effect = Effect("test", lambda _: 0.5).add_steps([sparkle(sparkle_count=0)])
    state = EffectState()

    effect.update(state, make_timer(0.1))

    for pos in [0.0, 0.25, 0.5, 0.75]:
        assert effect.value(state, pos) == pytest.approx(0.5)


def test_sparkle_output_does_not_decrease_below_input_value() -> None:
    # Sparkles add non-negative intensity; output can only increase.
    effect = Effect("test", lambda _: 0.4).add_steps([sparkle(sparkle_count=4, pixel_count=16)])
    state = EffectState()

    effect.update(state, make_timer(0.1))

    for pos in [0.0, 0.25, 0.5, 0.75]:
        assert effect.value(state, pos) >= 0.4


def test_sparkle_brightens_positions_above_base_value_at_peak_intensity() -> None:
    # With a non-zero base, sparkles add on top — they don't replace the base.
    # At peak intensity the sparkle position should exceed the base value.
    effect = Effect("test", lambda _: 0.4).add_steps(
        [
            sparkle(
                sparkle_count=1,
                spawn_delay_rate=0.0,
                fade_in_rate=100.0,
                pixel_count=10,
            )
        ]
    )
    state = EffectState()

    effect.update(state, make_timer(0.0))  # idle → fade_in (intensity still 0)
    effect.update(state, make_timer(1.0))  # fade_in raises intensity to 1.0

    max_value = max(effect.value(state, i / 10) for i in range(10))
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
                pixel_count=10,
            )
        ]
    )
    state = EffectState()

    effect.update(state, make_timer(0.0))  # idle → fade_in
    effect.update(state, make_timer(1.0))  # fade_in → 1.0 → fade_out
    effect.update(state, make_timer(1.0))  # fade_out → 0.0 → idle

    max_value = max(effect.value(state, i / 10) for i in range(10))
    assert max_value == pytest.approx(0.0)


def test_sparkle_adds_positive_value_after_spawn_delay_and_fade_in() -> None:
    # spawn_delay_rate=0 causes all sparkles to spawn on the first frame
    # and begin fading in on the second.
    effect = Effect("test", lambda _: 0.0).add_steps(
        [
            sparkle(
                sparkle_count=1,
                spawn_delay_rate=0.0,
                fade_in_rate=100.0,
                pixel_count=10,
            )
        ]
    )
    state = EffectState()

    effect.update(state, make_timer(0.0))  # frame 0: idle → fade_in (intensity still 0)
    effect.update(state, make_timer(1.0))  # frame 1: fade_in raises intensity to 1.0

    # Checking all buffer positions guarantees we hit the spawned sparkle.
    has_sparkle = any(effect.value(state, i / 10) > 0.0 for i in range(10))
    assert has_sparkle


def test_sparkle_collision_retry_gives_each_sparkle_a_distinct_position() -> None:
    # The collision-retry loop guarantees no two sparkles share a buffer slot.
    # After all sparkles reach peak intensity, exactly sparkle_count of the
    # buffer slots should be lit — impossible unless every sparkle landed at a
    # unique slot.
    sparkle_count = 3
    pixel_count = 4
    # SparkleStep allocates max(pixel_count, sparkle_count * 2) buffer slots;
    # sample at each slot boundary to count how many are lit.
    buffer_count = max(pixel_count, sparkle_count * 2)
    effect = Effect("test", lambda _: 0.0).add_steps(
        [
            sparkle(
                sparkle_count=sparkle_count,
                spawn_delay_rate=0.0,
                fade_in_rate=100.0,
                pixel_count=pixel_count,
            )
        ]
    )
    state = EffectState()

    effect.update(state, make_timer(0.0))  # idle → fade_in
    effect.update(state, make_timer(1.0))  # fade_in raises intensity to 1.0

    lit_count = sum(1 for i in range(buffer_count) if effect.value(state, i / buffer_count) > 0.0)
    assert lit_count == sparkle_count

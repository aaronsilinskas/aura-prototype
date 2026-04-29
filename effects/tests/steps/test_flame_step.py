import pytest
from effects.tests.helpers import make_timer

from effects.effect import Effect, EffectState
from effects.steps.flame import flame


def test_flame_output_is_always_at_least_as_large_as_input_value() -> None:
    # Flame blends additively; buffer values are always >= 0.
    effect = Effect("test", lambda _: 0.3).add_steps([flame(spark_count=4)])
    state = EffectState()

    effect.update(state, make_timer(0.1))

    for pos in [0.0, 0.25, 0.5, 0.75]:
        assert effect.value(state, pos) >= 0.3


def test_flame_output_saturates_at_one_under_heavy_heating() -> None:
    # With high heat_rate and spark_count, some positions will reach maximum.
    effect = Effect("test", lambda _: 0.0).add_steps(
        [flame(spark_count=4, heat_rate=100.0, resolution=16)]
    )
    state = EffectState()

    effect.update(state, make_timer(1.0))

    max_value = max(effect.value(state, i / 16) for i in range(16))
    assert max_value == pytest.approx(1.0)


def test_flame_with_no_sparks_produces_no_heat() -> None:
    effect = Effect("test", lambda _: 0.4).add_steps([flame(spark_count=0)])
    state = EffectState()

    effect.update(state, make_timer(0.1))

    for pos in [0.0, 0.25, 0.5, 0.75]:
        assert effect.value(state, pos) == pytest.approx(0.4)


def test_flame_sparks_respawn_to_keep_heat_active_over_multiple_cycles() -> None:
    # spark_count=1, heat_rate=3.0: each spark takes ~4 frames to max out,
    # then is removed and a new one spawns. The previous spark's heat lingers
    # for many frames (cool_rate is moderate). After 15 frames there should
    # always be non-zero heat from either the active spark or a recently cooled
    # position — verifying the respawn path keeps the flame alive.
    effect = Effect("test", lambda _: 0.0).add_steps(
        [flame(spark_count=1, heat_rate=3.0, resolution=8)]
    )
    state = EffectState()

    for _ in range(15):
        effect.update(state, make_timer(0.1))

    max_value = max(effect.value(state, i / 8) for i in range(8))
    assert max_value > 0.0


def test_flame_with_spread_heats_neighboring_cells_around_spark() -> None:
    # spread=1.0 gives half_flame_spread > 0, so the update loop heats cells
    # on both sides of each spark (not just the spark cell itself).
    # After one heavy heating frame multiple buffer positions should be non-zero.
    effect = Effect("test", lambda _: 0.0).add_steps(
        [flame(spark_count=1, heat_rate=100.0, resolution=8, spread=1.0)]
    )
    state = EffectState()

    effect.update(state, make_timer(1.0))

    hot_positions = sum(1 for i in range(8) if effect.value(state, i / 8) > 0.0)
    assert hot_positions > 1

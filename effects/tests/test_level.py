from effects.effect import EffectConfig
from effects.level import clamp_level, effect_level

# ---------------------------------------------------------------------------
# clamp_level
# ---------------------------------------------------------------------------


def test_clamp_level_returns_level_unchanged_within_valid_range() -> None:
    for level in range(1, 11):
        assert clamp_level(level) == level


def test_clamp_level_clamps_below_minimum_to_one() -> None:
    assert clamp_level(0) == 1
    assert clamp_level(-100) == 1


def test_clamp_level_clamps_above_maximum_to_ten() -> None:
    assert clamp_level(11) == 10
    assert clamp_level(100) == 10


# ---------------------------------------------------------------------------
# effect_level
# ---------------------------------------------------------------------------


def test_effect_level_defaults_to_one_when_option_missing() -> None:
    assert effect_level(EffectConfig(resolution=8)) == 1


def test_effect_level_returns_in_range_option_unchanged() -> None:
    for level in range(1, 11):
        assert effect_level(EffectConfig(resolution=8, options={"level": level})) == level


def test_effect_level_clamps_option_below_one_to_one() -> None:
    assert effect_level(EffectConfig(resolution=8, options={"level": 0})) == 1
    assert effect_level(EffectConfig(resolution=8, options={"level": -5})) == 1


def test_effect_level_clamps_option_above_ten_to_ten() -> None:
    assert effect_level(EffectConfig(resolution=8, options={"level": 11})) == 10
    assert effect_level(EffectConfig(resolution=8, options={"level": 99})) == 10

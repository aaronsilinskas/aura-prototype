import pytest

from effects.value import Range, ValueGenerator, lerp

# ---------------------------------------------------------------------------
# lerp
# ---------------------------------------------------------------------------


def test_lerp_returns_start_value_when_t_is_zero() -> None:
    assert lerp(10.0, 20.0, 0.0) == pytest.approx(10.0)


def test_lerp_returns_end_value_when_t_is_one() -> None:
    assert lerp(10.0, 20.0, 1.0) == pytest.approx(20.0)


def test_lerp_returns_midpoint_when_t_is_half() -> None:
    assert lerp(0.0, 1.0, 0.5) == pytest.approx(0.5)


def test_lerp_interpolates_proportionally_between_two_values() -> None:
    assert lerp(0.0, 100.0, 0.25) == pytest.approx(25.0)


def test_lerp_works_with_negative_range() -> None:
    assert lerp(-10.0, 10.0, 0.25) == pytest.approx(-5.0)
    assert lerp(-10.0, 10.0, 0.5) == pytest.approx(0.0)
    assert lerp(-10.0, 10.0, 0.75) == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# Range
# ---------------------------------------------------------------------------


def test_range_lerp_returns_start_at_zero_progress() -> None:
    r = Range(5.0, 15.0)

    assert r.lerp(0.0) == pytest.approx(5.0)


def test_range_lerp_returns_end_at_full_progress() -> None:
    r = Range(5.0, 15.0)

    assert r.lerp(1.0) == pytest.approx(15.0)


def test_range_lerp_clamps_to_end_when_progress_exceeds_one() -> None:
    r = Range(0.0, 1.0)

    assert r.lerp(1.5) == pytest.approx(1.0)
    assert r.lerp(100.0) == pytest.approx(1.0)


def test_range_lerp_interpolates_proportionally_at_midpoint() -> None:
    r = Range(0.0, 100.0)

    assert r.lerp(0.5) == pytest.approx(50.0)


def test_range_lerp_works_with_reversed_start_and_end() -> None:
    r = Range(1.0, 0.0)

    assert r.lerp(0.5) == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# ValueGenerator.resolve
# ---------------------------------------------------------------------------


def test_resolve_returns_float_unchanged() -> None:
    assert ValueGenerator.resolve(0.75) == pytest.approx(0.75)


def test_resolve_calls_callable_and_returns_its_result() -> None:
    assert ValueGenerator.resolve(lambda: 3.14) == pytest.approx(3.14)


def test_resolve_returns_zero_unchanged() -> None:
    assert ValueGenerator.resolve(0.0) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# ValueGenerator.random
# ---------------------------------------------------------------------------


def test_random_produces_values_within_specified_range() -> None:
    gen = ValueGenerator.random(0.2, 0.8)

    for _ in range(50):
        v = gen()
        assert 0.2 <= v <= 0.8


def test_random_uses_default_range_of_zero_to_one() -> None:
    gen = ValueGenerator.random()

    for _ in range(50):
        v = gen()
        assert 0.0 <= v <= 1.0


def test_random_produces_varying_values_across_calls() -> None:
    gen = ValueGenerator.random(0.0, 1.0)

    values = {gen() for _ in range(20)}
    assert len(values) > 1


# ---------------------------------------------------------------------------
# ValueGenerator.random_choice
# ---------------------------------------------------------------------------


def test_random_choice_only_returns_values_from_the_provided_list() -> None:
    choices = [0.1, 0.5, 0.9]
    gen = ValueGenerator.random_choice(choices)

    for _ in range(50):
        assert gen() in choices


def test_random_choice_returns_the_only_option_when_list_has_one_element() -> None:
    gen = ValueGenerator.random_choice([42.0])

    assert gen() == pytest.approx(42.0)


def test_random_choice_produces_varying_values_across_calls() -> None:
    choices = [1.0, 2.0, 3.0, 4.0, 5.0]
    gen = ValueGenerator.random_choice(choices)

    values = {gen() for _ in range(50)}
    assert len(values) > 1

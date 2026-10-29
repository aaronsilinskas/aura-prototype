"""Behaviour-driven tests for the opt-in ``neopixel_current_budget`` section (#948).

Every test goes through ``parse_device_config`` and asserts only on its public
result: the tuned strip/scope brightness and the parsed budget's fields.
"""

import pytest

from hardware.shared.device_config import parse_device_config


def _strip(pin: str, count: int, brightness: float, **extra) -> dict:
    entry = {
        "type": "neopixel",
        "pin": pin,
        "count": count,
        "brightness": brightness,
        "scope_pixels": {"personal": [0, count]},
    }
    entry.update(extra)
    return entry


def test_absent_budget_block_parses_to_none_and_leaves_brightness_as_declared():
    result = parse_device_config({"pixels": [_strip("D5", 100, 1.0)]})

    assert result.neopixel_current_budget is None
    assert result.pixels[0].strips[0].brightness == 1.0


def test_empty_budget_block_applies_default_limit_pixel_current_and_floor():
    result = parse_device_config({"pixels": [], "neopixel_current_budget": {}})

    budget = result.neopixel_current_budget
    assert budget.current_limit_ma == 2000
    assert budget.max_pixel_current_ma == 60
    assert budget.min_brightness == 0.05


def test_single_strip_over_budget_is_dimmed_to_draw_exactly_at_the_limit():
    # 100 px @ 1.0 x 60 mA = 6000 mA against a 2000 mA limit -> one third.
    result = parse_device_config(
        {
            "pixels": [_strip("D5", 100, 1.0)],
            "neopixel_current_budget": {"current_limit_ma": 2000},
        }
    )

    assert result.pixels[0].strips[0].brightness == pytest.approx(1 / 3)
    assert result.neopixel_current_budget.estimate_ma == pytest.approx(6000)
    assert result.neopixel_current_budget.scale == pytest.approx(1 / 3)


def test_legacy_scopes_strips_are_counted_and_scaled():
    # (30 px @ 0.5 + 10 px @ 1.0) x 60 mA = 1500 mA against 750 mA -> half.
    result = parse_device_config(
        {
            "pixels": [
                {
                    "type": "neopixel",
                    "scopes": {
                        "personal": {"pin": "D5", "count": 30, "brightness": 0.5},
                        "ambient": {"pin": "D6", "count": 10, "brightness": 1.0},
                    },
                }
            ],
            "neopixel_current_budget": {"current_limit_ma": 750},
        }
    )

    scopes = result.pixels[0].scopes
    assert scopes["personal"].brightness == pytest.approx(0.25)
    assert scopes["ambient"].brightness == pytest.approx(0.5)
    assert result.neopixel_current_budget.estimate_ma == pytest.approx(1500)


def test_disabled_strip_is_excluded_from_the_estimate_and_left_as_declared():
    # Only the enabled 10 px @ 1.0 counts: 600 mA, under the 1000 mA limit.
    result = parse_device_config(
        {
            "pixels": [
                _strip("D5", 10, 1.0),
                _strip("D6", 100, 1.0, enabled=False),
            ],
            "neopixel_current_budget": {"current_limit_ma": 1000},
        }
    )

    assert result.neopixel_current_budget.estimate_ma == pytest.approx(600)
    assert result.pixels[1].strips[0].brightness == 1.0


@pytest.mark.parametrize("field", ["current_limit_ma", "max_pixel_current_ma"])
@pytest.mark.parametrize("value", [1500.0, True, 0, -1, "2000"])
def test_milliamp_field_that_is_not_a_positive_int_raises_naming_the_field(field, value):
    with pytest.raises(ValueError, match=rf"neopixel_current_budget\.{field}"):
        parse_device_config({"neopixel_current_budget": {field: value}})


@pytest.mark.parametrize("value", [-0.1, 1.5, "0.1", True])
def test_min_brightness_outside_zero_to_one_raises_naming_the_field(value):
    with pytest.raises(ValueError, match=r"neopixel_current_budget\.min_brightness"):
        parse_device_config({"neopixel_current_budget": {"min_brightness": value}})


def test_unknown_key_in_budget_block_raises_naming_the_key():
    with pytest.raises(ValueError, match=r"neopixel_current_budget\.enabled is not a valid key"):
        parse_device_config({"neopixel_current_budget": {"enabled": True}})


def test_strips_on_separate_entries_share_one_scale_applied_to_each_declared_value():
    # (50 px @ 1.0 + 50 px @ 0.5) x 60 mA = 4500 mA against 1500 mA -> one third.
    result = parse_device_config(
        {
            "pixels": [_strip("D5", 50, 1.0), _strip("D6", 50, 0.5)],
            "neopixel_current_budget": {"current_limit_ma": 1500},
        }
    )

    assert result.pixels[0].strips[0].brightness == pytest.approx(1 / 3)
    assert result.pixels[1].strips[0].brightness == pytest.approx(1 / 6)
    assert result.neopixel_current_budget.scale == pytest.approx(1 / 3)


def test_strips_under_budget_keep_declared_brightness_with_scale_one():
    # 10 px @ 0.5 x 60 mA = 300 mA, well under the default 2000 mA.
    result = parse_device_config({"pixels": [_strip("D5", 10, 0.5)], "neopixel_current_budget": {}})

    assert result.pixels[0].strips[0].brightness == 0.5
    assert result.neopixel_current_budget.estimate_ma == pytest.approx(300)
    assert result.neopixel_current_budget.scale == 1.0


def test_matrix_entry_is_excluded_from_the_estimate_and_left_as_declared():
    result = parse_device_config(
        {
            "pixels": [
                {"type": "matrix", "cols": 13, "scope_rows": {"personal": [0, 9]}},
                _strip("D5", 10, 1.0),
            ],
            "neopixel_current_budget": {"current_limit_ma": 600},
        }
    )

    assert result.neopixel_current_budget.estimate_ma == pytest.approx(600)
    assert result.pixels[0].brightness == 1.0


def test_isolate_carries_the_budget_through_and_never_offers_it_as_a_keep():
    config = parse_device_config(
        {
            "pixels": [_strip("D5", 10, 1.0)],
            "audio": {"i2s_bit_clock": "D1", "i2s_word_select": "D2", "i2s_data": "D3"},
            "neopixel_current_budget": {},
        }
    )

    isolated = config.isolate("audio")

    assert isolated.neopixel_current_budget is config.neopixel_current_budget
    with pytest.raises(ValueError, match="is not valid"):
        config.isolate("neopixel_current_budget")


def test_strip_that_would_scale_below_the_floor_is_held_there_and_the_rest_absorb_the_cut():
    # #857's worked example: uniform scaling would put C at 0.056 < 0.1, so C is
    # held at 0.1 (600 mA) and A gets the remaining 1400 mA: 1400 / 6000.
    result = parse_device_config(
        {
            "pixels": [_strip("D5", 100, 1.0), _strip("D6", 100, 0.2)],
            "neopixel_current_budget": {"current_limit_ma": 2000, "min_brightness": 0.1},
        }
    )

    assert result.pixels[1].strips[0].brightness == pytest.approx(0.1)
    assert result.pixels[0].strips[0].brightness == pytest.approx(1400 / 6000)


def test_strip_declared_below_the_floor_keeps_its_declared_brightness():
    # B (100 px @ 0.05, under the 0.1 floor) is never scaled: it keeps 300 mA,
    # leaving A the remaining 1700 mA: 1700 / 6000.
    result = parse_device_config(
        {
            "pixels": [_strip("D5", 100, 1.0), _strip("D6", 100, 0.05)],
            "neopixel_current_budget": {"current_limit_ma": 2000, "min_brightness": 0.1},
        }
    )

    assert result.pixels[1].strips[0].brightness == 0.05


def test_holding_one_strip_at_the_floor_can_push_a_second_strip_under_it():
    # 100 px each @ 1.0 / 0.25 / 0.12, limit 3300 mA, floor 0.1. The first
    # scale (3300 / 8220) leaves B just above the floor but holds C; re-solving
    # for A and B (2700 / 7500 = 0.36) then puts B at 0.09, so B is held too,
    # leaving A (3300 - 600 - 600) / 6000 = 0.35.
    result = parse_device_config(
        {
            "pixels": [
                _strip("D5", 100, 1.0),
                _strip("D6", 100, 0.25),
                _strip("D7", 100, 0.12),
            ],
            "neopixel_current_budget": {"current_limit_ma": 3300, "min_brightness": 0.1},
        }
    )

    brightness = [entry.strips[0].brightness for entry in result.pixels]
    assert brightness == pytest.approx([0.35, 0.1, 0.1])


def test_limit_unreachable_even_at_the_floor_raises_naming_floor_current_limit_and_floor():
    # 200 px @ 0.1 x 60 mA = 1200 mA at the floor, over the 1000 mA limit.
    with pytest.raises(ValueError) as excinfo:
        parse_device_config(
            {
                "pixels": [_strip("D5", 200, 1.0)],
                "neopixel_current_budget": {"current_limit_ma": 1000, "min_brightness": 0.1},
            }
        )

    message = str(excinfo.value)
    assert "1200.0 mA" in message
    assert "1000 mA" in message
    assert "min_brightness 0.1" in message


def test_limit_met_exactly_at_the_floor_holds_every_strip_there():
    # 246 px @ 0.32 x 50 mA = 3936 mA at the floor -- exactly the limit.
    result = parse_device_config(
        {
            "pixels": [_strip("D5", 246, 0.898)],
            "neopixel_current_budget": {
                "current_limit_ma": 3936,
                "max_pixel_current_ma": 50,
                "min_brightness": 0.32,
            },
        }
    )

    assert result.pixels[0].strips[0].brightness == 0.32


def test_tuned_total_never_exceeds_the_limit_under_float_rounding():
    # Found by fuzzing: exact arithmetic lands on 15475 mA, plain float scaling
    # lands on 15475.000000000002.
    result = parse_device_config(
        {
            "pixels": [_strip("D5", 292, 0.849), _strip("D6", 33, 0.263)],
            "neopixel_current_budget": {
                "current_limit_ma": 15475,
                "max_pixel_current_ma": 64,
                "min_brightness": 0.38,
            },
        }
    )

    strips = [entry.strips[0] for entry in result.pixels]
    assert sum(strip.count * strip.brightness * 64 for strip in strips) <= 15475


def test_budget_records_the_shared_scale_applied_to_strips_not_held_at_the_floor():
    # #857's worked example: C is held at the floor, A is scaled by 1400 / 6000.
    result = parse_device_config(
        {
            "pixels": [_strip("D5", 100, 1.0), _strip("D6", 100, 0.2)],
            "neopixel_current_budget": {"current_limit_ma": 2000, "min_brightness": 0.1},
        }
    )

    assert result.neopixel_current_budget.scale == pytest.approx(1400 / 6000)


def test_budget_counts_strips_held_at_their_declared_value_or_at_the_floor():
    # B is declared at the 0.1 floor (held as declared); C would scale to
    # 0.25 x (2700 - 300) / 7500 = 0.08 (held at the floor); A absorbs the rest.
    result = parse_device_config(
        {
            "pixels": [
                _strip("D5", 100, 1.0),
                _strip("D6", 50, 0.1),
                _strip("D7", 100, 0.25),
            ],
            "neopixel_current_budget": {"current_limit_ma": 2700, "min_brightness": 0.1},
        }
    )

    assert result.neopixel_current_budget.at_min_brightness == 2


def test_strip_count_raised_beyond_its_declaration_is_budgeted_at_the_raised_count():
    # Declared 10 px @ 1.0 (600 mA) fits 2000 mA; a caller raising the count to
    # 100 px (6000 mA) in the mapping gets it dimmed to a third on re-parse.
    mapping = {
        "pixels": [_strip("D5", 10, 1.0)],
        "neopixel_current_budget": {"current_limit_ma": 2000},
    }
    mapping["pixels"][0]["count"] = 100

    result = parse_device_config(mapping)

    assert result.pixels[0].strips[0].count == 100
    assert result.pixels[0].strips[0].brightness == pytest.approx(1 / 3)
    assert result.neopixel_current_budget.estimate_ma == pytest.approx(6000)

from magic.aura import SpellLevelScaler


def test_scaler_defaults_to_value_coefficient_0_25_and_percentage_coefficient_0_05():
    scaler = SpellLevelScaler()
    assert scaler._value_coefficient == 0.25
    assert scaler._percentage_coefficient == 0.05


def test_scaler_keeps_custom_coefficients():
    scaler = SpellLevelScaler(value_coefficient=0.5, percentage_coefficient=0.1)
    assert scaler._value_coefficient == 0.5
    assert scaler._percentage_coefficient == 0.1


def test_negative_coefficients_clamp_to_zero_so_nothing_scales():
    scaler = SpellLevelScaler(value_coefficient=-0.5, percentage_coefficient=-0.1)
    assert scaler._value_coefficient == 0.0
    assert scaler._percentage_coefficient == 0.0
    assert scaler.scale_value(100, 5) == 100
    assert scaler.scale_percentage(0.5, 5) == 0.5


def test_scale_value_leaves_a_value_unchanged_at_level_one():
    scaler = SpellLevelScaler()
    assert scaler.scale_value(100, 1) == 100
    assert scaler.scale_value(50.5, 1) == 50.5
    assert scaler.scale_value(0, 1) == 0


def test_scale_value_adds_a_quarter_at_level_two():
    scaler = SpellLevelScaler()
    # Formula: value * (1 + 0.25 * (2 - 1)) = value * 1.25
    assert scaler.scale_value(100, 2) == 125
    assert scaler.scale_value(80, 2) == 100
    assert scaler.scale_value(40, 2) == 50


def test_scale_value_adds_a_quarter_per_level_above_one():
    scaler = SpellLevelScaler()
    # Level 3: value * (1 + 0.25 * 2) = value * 1.5
    assert scaler.scale_value(100, 3) == 150
    # Level 5: value * (1 + 0.25 * 4) = value * 2
    assert scaler.scale_value(100, 5) == 200
    # Level 10: value * (1 + 0.25 * 9) = value * 3.25
    assert scaler.scale_value(100, 10) == 325


def test_scale_value_uses_a_custom_value_coefficient():
    scaler = SpellLevelScaler(value_coefficient=0.5)
    # Level 2: value * (1 + 0.5 * 1) = value * 1.5
    assert scaler.scale_value(100, 2) == 150
    # Level 3: value * (1 + 0.5 * 2) = value * 2
    assert scaler.scale_value(100, 3) == 200


def test_scale_value_with_a_zero_coefficient_never_scales():
    scaler = SpellLevelScaler(value_coefficient=0)
    assert scaler.scale_value(100, 1) == 100
    assert scaler.scale_value(100, 5) == 100
    assert scaler.scale_value(100, 10) == 100


def test_scale_percentage_leaves_a_percentage_unchanged_at_level_one():
    scaler = SpellLevelScaler()
    assert scaler.scale_percentage(0.5, 1) == 0.5
    assert scaler.scale_percentage(0.2, 1) == 0.2
    assert scaler.scale_percentage(0.0, 1) == 0.0
    assert scaler.scale_percentage(1.0, 1) == 1.0


def test_scale_percentage_adds_five_points_at_level_two():
    scaler = SpellLevelScaler()
    # Formula: base + 0.05 * (2 - 1) = base + 0.05
    assert scaler.scale_percentage(0.5, 2) == 0.55
    assert scaler.scale_percentage(0.2, 2) == 0.25
    assert scaler.scale_percentage(0.0, 2) == 0.05


def test_scale_percentage_adds_five_points_per_level_above_one():
    scaler = SpellLevelScaler()
    # Level 3: base + 0.05 * 2 = base + 0.1
    assert scaler.scale_percentage(0.5, 3) == 0.6
    # Level 5: base + 0.05 * 4 = base + 0.2
    assert scaler.scale_percentage(0.5, 5) == 0.7
    # Level 10: base + 0.05 * 9 = base + 0.45
    assert scaler.scale_percentage(0.5, 10) == 0.95


def test_scale_percentage_clamps_at_one():
    scaler = SpellLevelScaler()
    # Level 21: 0.5 + 0.05 * 20 = 1.5, should clamp to 1.0
    assert scaler.scale_percentage(0.5, 21) == 1.0
    assert scaler.scale_percentage(1.0, 2) == 1.0
    assert scaler.scale_percentage(0.5, 100) == 1.0


def test_scale_percentage_scales_up_from_a_zero_base():
    scaler = SpellLevelScaler()
    assert scaler.scale_percentage(0.0, 1) == 0.0
    assert scaler.scale_percentage(0.0, 5) == 0.2


def test_scale_percentage_uses_a_custom_percentage_coefficient():
    scaler = SpellLevelScaler(percentage_coefficient=0.1)
    # Level 2: base + 0.1 * 1 = base + 0.1
    assert scaler.scale_percentage(0.5, 2) == 0.6
    # Level 3: base + 0.1 * 2 = base + 0.2
    assert scaler.scale_percentage(0.5, 3) == 0.7


def test_scale_percentage_with_a_zero_coefficient_never_scales():
    scaler = SpellLevelScaler(percentage_coefficient=0)
    assert scaler.scale_percentage(0.5, 1) == 0.5
    assert scaler.scale_percentage(0.5, 5) == 0.5
    assert scaler.scale_percentage(0.5, 10) == 0.5


def test_scale_value_scales_fractional_values():
    scaler = SpellLevelScaler()
    result = scaler.scale_value(33.33, 3)
    expected = 33.33 * 1.5
    assert abs(result - expected) < 0.01


def test_scale_percentage_scales_zero_and_tiny_bases_and_clamps_near_one():
    scaler = SpellLevelScaler()
    assert scaler.scale_percentage(0.0, 5) == 0.2, "a zero base still scales up"
    result = scaler.scale_percentage(0.01, 2)
    assert abs(result - 0.06) < 0.001, "a tiny base gains the same five points"
    assert scaler.scale_percentage(0.98, 2) == 1.0, "a base near one clamps at one"


def test_scalers_with_different_coefficients_scale_independently():
    scaler1 = SpellLevelScaler(value_coefficient=0.25)
    scaler2 = SpellLevelScaler(value_coefficient=0.5)

    assert scaler1.scale_value(100, 2) == 125
    assert scaler2.scale_value(100, 2) == 150

    assert scaler1._value_coefficient == 0.25
    assert scaler2._value_coefficient == 0.5

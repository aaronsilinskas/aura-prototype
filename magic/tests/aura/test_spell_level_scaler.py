from magic.aura import SpellLevelScaler


def test_default_coefficients():
    scaler = SpellLevelScaler()
    assert scaler._value_coefficient == 0.25
    assert scaler._percentage_coefficient == 0.05


def test_custom_coefficients():
    scaler = SpellLevelScaler(value_coefficient=0.5, percentage_coefficient=0.1)
    assert scaler._value_coefficient == 0.5
    assert scaler._percentage_coefficient == 0.1


def test_negative_coefficients_clamped():
    scaler = SpellLevelScaler(value_coefficient=-0.5, percentage_coefficient=-0.1)
    assert scaler._value_coefficient == 0.0
    assert scaler._percentage_coefficient == 0.0
    assert scaler.scale_value(100, 5) == 100
    assert scaler.scale_percentage(0.5, 5) == 0.5


def test_scale_value_level_one():
    scaler = SpellLevelScaler()
    assert scaler.scale_value(100, 1) == 100
    assert scaler.scale_value(50.5, 1) == 50.5
    assert scaler.scale_value(0, 1) == 0


def test_scale_value_level_two():
    scaler = SpellLevelScaler()
    # Formula: value * (1 + 0.25 * (2 - 1)) = value * 1.25
    assert scaler.scale_value(100, 2) == 125
    assert scaler.scale_value(80, 2) == 100
    assert scaler.scale_value(40, 2) == 50


def test_scale_value_higher_levels():
    scaler = SpellLevelScaler()
    # Level 3: value * (1 + 0.25 * 2) = value * 1.5
    assert scaler.scale_value(100, 3) == 150
    # Level 5: value * (1 + 0.25 * 4) = value * 2
    assert scaler.scale_value(100, 5) == 200
    # Level 10: value * (1 + 0.25 * 9) = value * 3.25
    assert scaler.scale_value(100, 10) == 325


def test_scale_value_custom_coefficient():
    scaler = SpellLevelScaler(value_coefficient=0.5)
    # Level 2: value * (1 + 0.5 * 1) = value * 1.5
    assert scaler.scale_value(100, 2) == 150
    # Level 3: value * (1 + 0.5 * 2) = value * 2
    assert scaler.scale_value(100, 3) == 200


def test_scale_value_zero_coefficient():
    scaler = SpellLevelScaler(value_coefficient=0)
    assert scaler.scale_value(100, 1) == 100
    assert scaler.scale_value(100, 5) == 100
    assert scaler.scale_value(100, 10) == 100


def test_scale_percentage_level_one():
    scaler = SpellLevelScaler()
    assert scaler.scale_percentage(0.5, 1) == 0.5
    assert scaler.scale_percentage(0.2, 1) == 0.2
    assert scaler.scale_percentage(0.0, 1) == 0.0
    assert scaler.scale_percentage(1.0, 1) == 1.0


def test_scale_percentage_level_two():
    scaler = SpellLevelScaler()
    # Formula: base + 0.05 * (2 - 1) = base + 0.05
    assert scaler.scale_percentage(0.5, 2) == 0.55
    assert scaler.scale_percentage(0.2, 2) == 0.25
    assert scaler.scale_percentage(0.0, 2) == 0.05


def test_scale_percentage_higher_levels():
    scaler = SpellLevelScaler()
    # Level 3: base + 0.05 * 2 = base + 0.1
    assert scaler.scale_percentage(0.5, 3) == 0.6
    # Level 5: base + 0.05 * 4 = base + 0.2
    assert scaler.scale_percentage(0.5, 5) == 0.7
    # Level 10: base + 0.05 * 9 = base + 0.45
    assert scaler.scale_percentage(0.5, 10) == 0.95


def test_scale_percentage_clamp_upper():
    scaler = SpellLevelScaler()
    # Level 21: 0.5 + 0.05 * 20 = 1.5, should clamp to 1.0
    assert scaler.scale_percentage(0.5, 21) == 1.0
    assert scaler.scale_percentage(1.0, 2) == 1.0
    assert scaler.scale_percentage(0.5, 100) == 1.0


def test_scale_percentage_clamp_lower():
    scaler = SpellLevelScaler()
    assert scaler.scale_percentage(0.0, 1) == 0.0
    assert scaler.scale_percentage(0.0, 5) == 0.2


def test_scale_percentage_custom_coefficient():
    scaler = SpellLevelScaler(percentage_coefficient=0.1)
    # Level 2: base + 0.1 * 1 = base + 0.1
    assert scaler.scale_percentage(0.5, 2) == 0.6
    # Level 3: base + 0.1 * 2 = base + 0.2
    assert scaler.scale_percentage(0.5, 3) == 0.7


def test_scale_percentage_zero_coefficient():
    scaler = SpellLevelScaler(percentage_coefficient=0)
    assert scaler.scale_percentage(0.5, 1) == 0.5
    assert scaler.scale_percentage(0.5, 5) == 0.5
    assert scaler.scale_percentage(0.5, 10) == 0.5


def test_scale_value_with_floats():
    scaler = SpellLevelScaler()
    result = scaler.scale_value(33.33, 3)
    expected = 33.33 * 1.5
    assert abs(result - expected) < 0.01


def test_scale_percentage_edge_cases():
    scaler = SpellLevelScaler()
    assert scaler.scale_percentage(0.0, 5) == 0.2
    result = scaler.scale_percentage(0.01, 2)
    assert abs(result - 0.06) < 0.001
    assert scaler.scale_percentage(0.98, 2) == 1.0


def test_multiple_scalers_independent():
    scaler1 = SpellLevelScaler(value_coefficient=0.25)
    scaler2 = SpellLevelScaler(value_coefficient=0.5)

    assert scaler1.scale_value(100, 2) == 125
    assert scaler2.scale_value(100, 2) == 150

    assert scaler1._value_coefficient == 0.25
    assert scaler2._value_coefficient == 0.5

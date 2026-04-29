from magic.aura import SpellLevelScaler


def test_default_coefficients():
    """Test that default coefficients are set correctly."""
    scaler = SpellLevelScaler()
    assert scaler._value_coefficient == 0.25
    assert scaler._percentage_coefficient == 0.05


def test_custom_coefficients():
    """Test that custom coefficients are set correctly."""
    scaler = SpellLevelScaler(value_coefficient=0.5, percentage_coefficient=0.1)
    assert scaler._value_coefficient == 0.5
    assert scaler._percentage_coefficient == 0.1


def test_negative_coefficients_clamped():
    """Test that negative coefficients are clamped to 0."""
    scaler = SpellLevelScaler(value_coefficient=-0.5, percentage_coefficient=-0.1)
    assert scaler._value_coefficient == 0.0
    assert scaler._percentage_coefficient == 0.0
    # With clamped coefficients, no scaling should occur
    assert scaler.scale_value(100, 5) == 100
    assert scaler.scale_percentage(0.5, 5) == 0.5


def test_scale_value_level_one():
    """Test that scaling a value at level 1 returns the original value."""
    scaler = SpellLevelScaler()
    assert scaler.scale_value(100, 1) == 100
    assert scaler.scale_value(50.5, 1) == 50.5
    assert scaler.scale_value(0, 1) == 0


def test_scale_value_level_two():
    """Test scaling a value at level 2 with default coefficient."""
    scaler = SpellLevelScaler()
    # Formula: value * (1 + 0.25 * (2 - 1)) = value * 1.25
    assert scaler.scale_value(100, 2) == 125
    assert scaler.scale_value(80, 2) == 100
    assert scaler.scale_value(40, 2) == 50


def test_scale_value_higher_levels():
    """Test scaling values at higher levels."""
    scaler = SpellLevelScaler()
    # Level 3: value * (1 + 0.25 * 2) = value * 1.5
    assert scaler.scale_value(100, 3) == 150
    # Level 5: value * (1 + 0.25 * 4) = value * 2
    assert scaler.scale_value(100, 5) == 200
    # Level 10: value * (1 + 0.25 * 9) = value * 3.25
    assert scaler.scale_value(100, 10) == 325


def test_scale_value_custom_coefficient():
    """Test scaling with custom value coefficient."""
    scaler = SpellLevelScaler(value_coefficient=0.5)
    # Level 2: value * (1 + 0.5 * 1) = value * 1.5
    assert scaler.scale_value(100, 2) == 150
    # Level 3: value * (1 + 0.5 * 2) = value * 2
    assert scaler.scale_value(100, 3) == 200


def test_scale_value_zero_coefficient():
    """Test that zero coefficient results in no scaling."""
    scaler = SpellLevelScaler(value_coefficient=0)
    assert scaler.scale_value(100, 1) == 100
    assert scaler.scale_value(100, 5) == 100
    assert scaler.scale_value(100, 10) == 100


def test_scale_percentage_level_one():
    """Test that scaling a percentage at level 1 returns the original value."""
    scaler = SpellLevelScaler()
    assert scaler.scale_percentage(0.5, 1) == 0.5
    assert scaler.scale_percentage(0.2, 1) == 0.2
    assert scaler.scale_percentage(0.0, 1) == 0.0
    assert scaler.scale_percentage(1.0, 1) == 1.0


def test_scale_percentage_level_two():
    """Test scaling a percentage at level 2 with default coefficient."""
    scaler = SpellLevelScaler()
    # Formula: base + 0.05 * (2 - 1) = base + 0.05
    assert scaler.scale_percentage(0.5, 2) == 0.55
    assert scaler.scale_percentage(0.2, 2) == 0.25
    assert scaler.scale_percentage(0.0, 2) == 0.05


def test_scale_percentage_higher_levels():
    """Test scaling percentages at higher levels."""
    scaler = SpellLevelScaler()
    # Level 3: base + 0.05 * 2 = base + 0.1
    assert scaler.scale_percentage(0.5, 3) == 0.6
    # Level 5: base + 0.05 * 4 = base + 0.2
    assert scaler.scale_percentage(0.5, 5) == 0.7
    # Level 10: base + 0.05 * 9 = base + 0.45
    assert scaler.scale_percentage(0.5, 10) == 0.95


def test_scale_percentage_clamp_upper():
    """Test that percentage scaling clamps at 1.0."""
    scaler = SpellLevelScaler()
    # Level 21: 0.5 + 0.05 * 20 = 1.5, should clamp to 1.0
    assert scaler.scale_percentage(0.5, 21) == 1.0
    # Already at 1.0
    assert scaler.scale_percentage(1.0, 2) == 1.0
    # Level 100 should still clamp to 1.0
    assert scaler.scale_percentage(0.5, 100) == 1.0


def test_scale_percentage_clamp_lower():
    """Test that percentage scaling does not go below 0.0."""
    scaler = SpellLevelScaler()
    # Test with base percentage of 0.0
    assert scaler.scale_percentage(0.0, 1) == 0.0
    assert scaler.scale_percentage(0.0, 5) == 0.2


def test_scale_percentage_custom_coefficient():
    """Test scaling with custom percentage coefficient."""
    scaler = SpellLevelScaler(percentage_coefficient=0.1)
    # Level 2: base + 0.1 * 1 = base + 0.1
    assert scaler.scale_percentage(0.5, 2) == 0.6
    # Level 3: base + 0.1 * 2 = base + 0.2
    assert scaler.scale_percentage(0.5, 3) == 0.7


def test_scale_percentage_zero_coefficient():
    """Test that zero coefficient results in no percentage scaling."""
    scaler = SpellLevelScaler(percentage_coefficient=0)
    assert scaler.scale_percentage(0.5, 1) == 0.5
    assert scaler.scale_percentage(0.5, 5) == 0.5
    assert scaler.scale_percentage(0.5, 10) == 0.5


def test_scale_value_with_floats():
    """Test that scale_value works correctly with floating point values."""
    scaler = SpellLevelScaler()
    # Test with decimal values
    result = scaler.scale_value(33.33, 3)
    expected = 33.33 * 1.5
    assert abs(result - expected) < 0.01


def test_scale_percentage_edge_cases():
    """Test edge cases for percentage scaling."""
    scaler = SpellLevelScaler()
    # Starting at 0 should still scale up
    assert scaler.scale_percentage(0.0, 5) == 0.2
    # Very small base value
    result = scaler.scale_percentage(0.01, 2)
    assert abs(result - 0.06) < 0.001
    # Close to upper limit
    assert scaler.scale_percentage(0.98, 2) == 1.0


def test_multiple_scalers_independent():
    """Test that multiple scaler instances are independent."""
    scaler1 = SpellLevelScaler(value_coefficient=0.25)
    scaler2 = SpellLevelScaler(value_coefficient=0.5)

    # Both should scale independently
    assert scaler1.scale_value(100, 2) == 125
    assert scaler2.scale_value(100, 2) == 150

    # Verify coefficients haven't changed
    assert scaler1._value_coefficient == 0.25
    assert scaler2._value_coefficient == 0.5

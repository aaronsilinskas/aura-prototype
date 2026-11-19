from magic.values import ValueModifier


def test_value_modifier_init():
    mod = ValueModifier(multiplier=2.5, duration=10.0)
    assert mod.multiplier == 2.5
    assert mod.duration.length == 10.0
    assert mod.duration.elapsed == 0.0


def test_value_modifier_update_not_expired():
    mod = ValueModifier(multiplier=1.0, duration=5.0)
    result = mod.update(2.0)
    assert result is False
    assert mod.duration.elapsed == 2.0


def test_value_modifier_update_expired():
    mod = ValueModifier(multiplier=1.0, duration=5.0)
    result = mod.update(5.0)
    assert result is True
    assert mod.duration.elapsed == 5.0


def test_value_modifier_update_over_expired():
    mod = ValueModifier(multiplier=1.0, duration=5.0)
    result = mod.update(6.0)
    assert result is True
    assert mod.duration.elapsed == 6.0


def test_value_modifier_update_accumulation():
    mod = ValueModifier(multiplier=1.0, duration=10.0)
    mod.update(3.0)
    mod.update(4.0)
    mod.update(3.0)
    assert mod.duration.elapsed == 10.0
    assert mod.update(1.0) is True


def test_value_modifier_multiplier_setter():
    mod = ValueModifier(multiplier=2.0, duration=10.0)
    assert mod.multiplier == 2.0

    mod.multiplier = 3.5
    assert mod.multiplier == 3.5


def test_value_modifier_multiplier_setter_with_zero():
    mod = ValueModifier(multiplier=2.0, duration=10.0)
    mod.multiplier = 0.0
    assert mod.multiplier == 0.0


def test_value_modifier_multiplier_setter_with_negative():
    mod = ValueModifier(multiplier=2.0, duration=10.0)
    mod.multiplier = -1.5
    assert mod.multiplier == -1.5


def test_value_modifier_multiplier_setter_preserves_duration():
    mod = ValueModifier(multiplier=2.0, duration=10.0)
    mod.update(3.0)

    mod.multiplier = 4.0

    assert mod.multiplier == 4.0
    assert mod.duration.elapsed == 3.0
    assert mod.duration.length == 10.0

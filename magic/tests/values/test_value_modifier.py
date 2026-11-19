from magic.values import ValueModifier


def test_a_new_value_modifier_keeps_its_multiplier_and_length_with_nothing_elapsed():
    mod = ValueModifier(multiplier=2.5, duration=10.0)
    assert mod.multiplier == 2.5
    assert mod.duration.length == 10.0
    assert mod.duration.elapsed == 0.0


def test_value_modifier_is_not_expired_before_its_duration_passes():
    mod = ValueModifier(multiplier=1.0, duration=5.0)
    result = mod.update(2.0)
    assert result is False
    assert mod.duration.elapsed == 2.0


def test_value_modifier_expires_when_exactly_its_duration_passes():
    mod = ValueModifier(multiplier=1.0, duration=5.0)
    result = mod.update(5.0)
    assert result is True
    assert mod.duration.elapsed == 5.0


def test_value_modifier_expires_when_updated_past_its_duration():
    mod = ValueModifier(multiplier=1.0, duration=5.0)
    result = mod.update(6.0)
    assert result is True
    assert mod.duration.elapsed == 6.0


def test_value_modifier_accumulates_elapsed_time_across_updates():
    mod = ValueModifier(multiplier=1.0, duration=10.0)
    mod.update(3.0)
    mod.update(4.0)
    mod.update(3.0)
    assert mod.duration.elapsed == 10.0
    assert mod.update(1.0) is True


def test_value_modifier_multiplier_can_be_changed():
    mod = ValueModifier(multiplier=2.0, duration=10.0)
    assert mod.multiplier == 2.0

    mod.multiplier = 3.5
    assert mod.multiplier == 3.5


def test_value_modifier_multiplier_can_be_set_to_zero():
    mod = ValueModifier(multiplier=2.0, duration=10.0)
    mod.multiplier = 0.0
    assert mod.multiplier == 0.0


def test_value_modifier_multiplier_can_be_set_negative():
    mod = ValueModifier(multiplier=2.0, duration=10.0)
    mod.multiplier = -1.5
    assert mod.multiplier == -1.5


def test_changing_the_multiplier_leaves_the_duration_unchanged():
    mod = ValueModifier(multiplier=2.0, duration=10.0)
    mod.update(3.0)

    mod.multiplier = 4.0

    assert mod.multiplier == 4.0
    assert mod.duration.elapsed == 3.0
    assert mod.duration.length == 10.0

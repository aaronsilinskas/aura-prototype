from magic.values import MinMaxValue, ValueModifier


def test_initialization():
    m = MinMaxValue(value=10, min=0, max=20)
    assert m.value == 10
    assert m.min == 0
    assert m.max.value == 20


def test_clamping_below_min():
    m = MinMaxValue(value=10, min=0, max=20)
    m.value = -5
    assert m.value == 0


def test_clamping_above_max():
    m = MinMaxValue(value=10, min=0, max=20)
    m.value = 25
    assert m.value == 20


def test_clamping_min_update():
    m = MinMaxValue(value=10, min=0, max=20)
    m.min = 15
    assert m.value == 15


def test_clamping_max_update():
    m = MinMaxValue(value=10, min=0, max=20)
    m.max.base = 5
    assert m.value == 5


def test_setting_value_within_bounds():
    m = MinMaxValue(value=10, min=0, max=20)
    m.value = 15
    assert m.value == 15


def test_add_max_modifier():
    m = MinMaxValue(value=10, min=0, max=20)
    m.max.modifiers.add(ValueModifier(multiplier=2.0, duration=10.0))
    assert m.max.value == 40.0


def test_max_modifier_clamps_value():
    m = MinMaxValue(value=10, min=0, max=20)
    m.max.modifiers.add(ValueModifier(multiplier=2.0, duration=10.0))
    m.value = 50
    assert m.value == 40.0


def test_removed_max_modifier_clamps_value():
    m = MinMaxValue(value=10, min=0, max=20)
    mod = ValueModifier(multiplier=2.0, duration=10.0)
    m.max.modifiers.add(mod)
    m.value = 40
    m.max.modifiers.remove(mod)
    assert m.max.value == 20.0
    assert m.value == 20.0


def test_update_triggers_max_modifier_update():
    m = MinMaxValue(value=10, min=0, max=20)
    mod = ValueModifier(multiplier=2.0, duration=1.0)
    m.max.modifiers.add(mod)
    assert m.max.value == 40.0
    m.update(1.5)  # Update with elapsed time greater than modifier duration
    assert m.max.value == 20.0

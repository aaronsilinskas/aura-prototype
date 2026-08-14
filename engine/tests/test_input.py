"""Tests for ButtonData query methods, MagneticData, and InputEvents.Sensors."""

from engine.input import AccelerationData, ButtonData, InputEvents, MagneticData


def _make(states: dict[str, int]) -> ButtonData:
    return ButtonData(states=states)


# ---------------------------------------------------------------------------
# is_pressed
# ---------------------------------------------------------------------------


def test_is_pressed_returns_true_when_state_is_pressed():
    bd = _make({"A": ButtonData.PRESSED})
    assert bd.is_pressed("A") is True


def test_is_pressed_returns_false_when_state_is_down():
    bd = _make({"A": ButtonData.DOWN})
    assert bd.is_pressed("A") is False


def test_is_pressed_returns_false_when_state_is_up():
    bd = _make({"A": ButtonData.UP})
    assert bd.is_pressed("A") is False


def test_is_pressed_returns_false_when_state_is_released():
    bd = _make({"A": ButtonData.RELEASED})
    assert bd.is_pressed("A") is False


def test_is_pressed_returns_false_for_unknown_button():
    bd = _make({})
    assert bd.is_pressed("X") is False


# ---------------------------------------------------------------------------
# is_released
# ---------------------------------------------------------------------------


def test_is_released_returns_true_when_state_is_released():
    bd = _make({"A": ButtonData.RELEASED})
    assert bd.is_released("A") is True


def test_is_released_returns_false_when_state_is_up():
    bd = _make({"A": ButtonData.UP})
    assert bd.is_released("A") is False


def test_is_released_returns_false_when_state_is_down():
    bd = _make({"A": ButtonData.DOWN})
    assert bd.is_released("A") is False


def test_is_released_returns_false_when_state_is_pressed():
    bd = _make({"A": ButtonData.PRESSED})
    assert bd.is_released("A") is False


def test_is_released_returns_false_for_unknown_button():
    bd = _make({})
    assert bd.is_released("X") is False


# ---------------------------------------------------------------------------
# is_down  (PRESSED or DOWN)
# ---------------------------------------------------------------------------


def test_is_down_returns_true_when_state_is_down():
    bd = _make({"A": ButtonData.DOWN})
    assert bd.is_down("A") is True


def test_is_down_returns_true_when_state_is_pressed():
    bd = _make({"A": ButtonData.PRESSED})
    assert bd.is_down("A") is True


def test_is_down_returns_false_when_state_is_up():
    bd = _make({"A": ButtonData.UP})
    assert bd.is_down("A") is False


def test_is_down_returns_false_when_state_is_released():
    bd = _make({"A": ButtonData.RELEASED})
    assert bd.is_down("A") is False


def test_is_down_returns_false_for_unknown_button():
    bd = _make({})
    assert bd.is_down("X") is False


# ---------------------------------------------------------------------------
# is_up  (UP or RELEASED)
# ---------------------------------------------------------------------------


def test_is_up_returns_true_when_state_is_up():
    bd = _make({"A": ButtonData.UP})
    assert bd.is_up("A") is True


def test_is_up_returns_true_when_state_is_released():
    bd = _make({"A": ButtonData.RELEASED})
    assert bd.is_up("A") is True


def test_is_up_returns_false_when_state_is_down():
    bd = _make({"A": ButtonData.DOWN})
    assert bd.is_up("A") is False


def test_is_up_returns_false_when_state_is_pressed():
    bd = _make({"A": ButtonData.PRESSED})
    assert bd.is_up("A") is False


def test_is_up_returns_false_for_unknown_button():
    bd = _make({})
    assert bd.is_up("X") is False


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


def test_get_returns_raw_state_constant_for_known_button():
    bd = _make({"A": ButtonData.DOWN})
    assert bd.get("A") == ButtonData.DOWN


def test_get_returns_none_for_unknown_button():
    bd = _make({})
    assert bd.get("X") is None


# ---------------------------------------------------------------------------
# items
# ---------------------------------------------------------------------------


def test_items_returns_all_button_state_pairs():
    bd = _make({"A": ButtonData.PRESSED, "B": ButtonData.UP})
    assert set(bd.items()) == {("A", ButtonData.PRESSED), ("B", ButtonData.UP)}


def test_items_is_empty_when_no_buttons():
    bd = _make({})
    assert list(bd.items()) == []


# ---------------------------------------------------------------------------
# set
# ---------------------------------------------------------------------------


def test_set_stores_state_for_new_button():
    bd = _make({})
    bd.set("A", ButtonData.PRESSED)
    assert bd.is_pressed("A") is True


def test_set_overwrites_existing_state():
    bd = _make({"A": ButtonData.UP})
    bd.set("A", ButtonData.DOWN)
    assert bd.is_down("A") is True


def test_set_multiple_buttons_independently():
    bd = _make({})
    bd.set("A", ButtonData.PRESSED)
    bd.set("B", ButtonData.UP)
    assert bd.is_pressed("A") is True
    assert bd.is_up("B") is True


# ---------------------------------------------------------------------------
# MagneticData
# ---------------------------------------------------------------------------


def test_magnetic_data_defaults_all_axes_to_zero():
    magnetic = MagneticData()

    assert (magnetic.x, magnetic.y, magnetic.z) == (0.0, 0.0, 0.0)


def test_magnetic_data_holds_provided_axis_values():
    magnetic = MagneticData(x=12.5, y=-3.25, z=48.0)

    assert (magnetic.x, magnetic.y, magnetic.z) == (12.5, -3.25, 48.0)


def test_magnetic_data_str_reports_all_axes():
    magnetic = MagneticData(x=1.0, y=2.0, z=3.0)

    assert str(magnetic) == "MagneticData(x=1.0, y=2.0, z=3.0)"


# ---------------------------------------------------------------------------
# InputEvents.Sensors
# ---------------------------------------------------------------------------


def test_sensors_event_carries_buttons_acceleration_and_magnetic():
    buttons = ButtonData(states={"A": ButtonData.PRESSED})
    acceleration = AccelerationData(x=1.0, y=2.0, z=3.0)
    magnetic = MagneticData(x=4.0, y=5.0, z=6.0)

    event = InputEvents.Sensors(buttons, acceleration, magnetic)

    assert event.buttons is buttons
    assert event.acceleration is acceleration
    assert event.magnetic is magnetic


def test_sensors_event_defaults_acceleration_and_magnetic_to_none():
    buttons = ButtonData(states={})

    event = InputEvents.Sensors(buttons)

    assert event.acceleration is None
    assert event.magnetic is None


def test_sensors_event_verb_is_sensors():
    event = InputEvents.Sensors(ButtonData(states={}))

    assert event.name == "sensors"

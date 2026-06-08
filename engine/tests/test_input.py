"""Tests for ButtonData query methods and _states encapsulation."""

from engine.input import ButtonData


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

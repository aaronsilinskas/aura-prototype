from engine.input import ButtonData
from hardware.shared.debounced_buttons import DebouncedButtons


def _out() -> ButtonData:
    return ButtonData({})


def test_button_is_up_when_pin_is_high_at_boot():
    buttons = DebouncedButtons([("A", lambda: True)], interval=0)
    out = _out()
    buttons.update(0.0, out)
    assert out.is_up("A")


def test_button_is_down_when_pin_is_low_at_boot():
    buttons = DebouncedButtons([("A", lambda: False)], interval=0)
    out = _out()
    buttons.update(0.0, out)
    assert out.is_down("A")


def test_button_is_pressed_on_falling_edge_committed():
    pin = [True]
    buttons = DebouncedButtons([("A", lambda: pin[0])], interval=0)
    out = _out()

    pin[0] = False
    buttons.update(0.0, out)

    assert out.is_pressed("A")


def test_button_is_released_on_rising_edge_committed():
    pin = [False]
    buttons = DebouncedButtons([("A", lambda: pin[0])], interval=0)
    out = _out()
    buttons.update(0.0, out)  # settle into DOWN state

    pin[0] = True
    buttons.update(0.0, out)

    assert out.is_released("A")


def test_button_becomes_down_not_pressed_when_held_after_press_edge():
    pin = [True]
    buttons = DebouncedButtons([("A", lambda: pin[0])], interval=0)
    out = _out()
    pin[0] = False
    buttons.update(0.0, out)  # PRESSED

    buttons.update(0.1, out)  # stable low, no pending edge

    assert out.is_down("A")
    assert not out.is_pressed("A")


def test_button_becomes_up_not_released_when_stable_after_release_edge():
    pin = [False]
    buttons = DebouncedButtons([("A", lambda: pin[0])], interval=0)
    out = _out()
    buttons.update(0.0, out)  # DOWN
    pin[0] = True
    buttons.update(0.0, out)  # RELEASED

    buttons.update(0.1, out)  # stable high, no pending edge

    assert out.is_up("A")
    assert not out.is_released("A")


def test_bounce_before_debounce_interval_does_not_commit_edge():
    pin = [True]
    buttons = DebouncedButtons([("A", lambda: pin[0])], interval=0.1)
    out = _out()

    pin[0] = False  # press
    buttons.update(0.05, out)  # 0.05 < 0.1, no commit yet
    pin[0] = True  # bounce back — resets candidate
    buttons.update(0.03, out)
    pin[0] = False  # press again
    buttons.update(0.03, out)  # only 0.03 accumulated since last reset

    assert out.is_up("A")


def test_button_is_pressed_when_edge_held_for_full_debounce_interval():
    pin = [True]
    buttons = DebouncedButtons([("A", lambda: pin[0])], interval=0.1)
    out = _out()
    pin[0] = False

    buttons.update(0.05, out)  # 0.05 accumulated, no commit yet
    buttons.update(0.06, out)  # total 0.11 >= 0.1, commits PRESSED

    assert out.is_pressed("A")


def test_button_held_low_at_boot_reads_as_down_not_pressed():
    pin = [False]  # button already held down at power-on
    buttons = DebouncedButtons([("A", lambda: pin[0])], interval=0.1)
    out = _out()

    buttons.update(0.2, out)  # elapsed > interval but settled == candidate, no edge

    assert out.is_down("A")
    assert not out.is_pressed("A")


def test_two_buttons_track_their_own_states_independently():
    pin_a = [True]
    pin_b = [False]
    buttons = DebouncedButtons(
        [("A", lambda: pin_a[0]), ("B", lambda: pin_b[0])],
        interval=0,
    )
    out = _out()

    pin_a[0] = False  # A pressed; B stays low
    buttons.update(0.0, out)

    assert out.is_pressed("A")
    assert out.is_down("B")
    assert not out.is_pressed("B")


def test_out_buffer_reflects_latest_pin_state_on_successive_updates():
    pin = [True]
    buttons = DebouncedButtons([("A", lambda: pin[0])], interval=0)
    out = _out()

    buttons.update(0.0, out)

    pin[0] = False
    buttons.update(0.0, out)

    assert out.is_pressed("A")

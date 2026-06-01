from engine.input import ButtonData
from hardware.shared.debounced_buttons import DebouncedButtons


def test_update_returns_up_when_pin_high_at_boot():
    buttons = DebouncedButtons([("A", lambda: True)], interval=0)
    result = buttons.update(0.0)
    assert result.states["A"] == ButtonData.UP


def test_update_returns_down_when_pin_low_at_boot():
    buttons = DebouncedButtons([("A", lambda: False)], interval=0)
    result = buttons.update(0.0)
    assert result.states["A"] == ButtonData.DOWN


def test_update_returns_pressed_on_falling_edge_committed():
    pin = [True]
    buttons = DebouncedButtons([("A", lambda: pin[0])], interval=0)

    pin[0] = False
    result = buttons.update(0.0)

    assert result.states["A"] == ButtonData.PRESSED


def test_update_returns_released_on_rising_edge_committed():
    pin = [False]
    buttons = DebouncedButtons([("A", lambda: pin[0])], interval=0)
    buttons.update(0.0)  # settle into DOWN state

    pin[0] = True
    result = buttons.update(0.0)

    assert result.states["A"] == ButtonData.RELEASED


def test_update_returns_down_when_stably_low_after_press_edge():
    pin = [True]
    buttons = DebouncedButtons([("A", lambda: pin[0])], interval=0)
    pin[0] = False
    buttons.update(0.0)  # PRESSED

    result = buttons.update(0.1)  # stable low, no pending edge

    assert result.states["A"] == ButtonData.DOWN


def test_update_returns_up_when_stably_high_after_release_edge():
    pin = [False]
    buttons = DebouncedButtons([("A", lambda: pin[0])], interval=0)
    buttons.update(0.0)  # DOWN
    pin[0] = True
    buttons.update(0.0)  # RELEASED

    result = buttons.update(0.1)  # stable high, no pending edge

    assert result.states["A"] == ButtonData.UP


def test_noise_rejection_bounce_before_interval_does_not_commit():
    pin = [True]
    buttons = DebouncedButtons([("A", lambda: pin[0])], interval=0.1)

    pin[0] = False  # press
    buttons.update(0.05)  # 0.05 < 0.1, no commit yet
    pin[0] = True  # bounce back — resets candidate
    buttons.update(0.03)
    pin[0] = False  # press again
    result = buttons.update(0.03)  # only 0.03 accumulated since last reset

    assert result.states["A"] == ButtonData.UP


def test_falling_edge_committed_after_full_interval():
    pin = [True]
    buttons = DebouncedButtons([("A", lambda: pin[0])], interval=0.1)
    pin[0] = False

    buttons.update(0.05)  # 0.05 accumulated, no commit yet
    result = buttons.update(0.06)  # total 0.11 >= 0.1, commits PRESSED

    assert result.states["A"] == ButtonData.PRESSED


def test_pin_held_low_at_boot_returns_down_not_pressed():
    pin = [False]  # button already held down at power-on
    buttons = DebouncedButtons([("A", lambda: pin[0])], interval=0.1)

    result = buttons.update(0.2)  # elapsed > interval but settled == candidate, no edge

    assert result.states["A"] == ButtonData.DOWN


def test_multiple_buttons_produce_independent_states():
    pin_a = [True]
    pin_b = [False]
    buttons = DebouncedButtons(
        [("A", lambda: pin_a[0]), ("B", lambda: pin_b[0])],
        interval=0,
    )

    pin_a[0] = False  # A pressed; B stays low
    result = buttons.update(0.0)

    assert result.states["A"] == ButtonData.PRESSED
    assert result.states["B"] == ButtonData.DOWN

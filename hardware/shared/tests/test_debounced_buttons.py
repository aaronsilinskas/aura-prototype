from hardware.shared.debounced_buttons import DebouncedButtons


def test_button_is_up_when_pin_is_high_at_boot():
    buttons = DebouncedButtons([("A", lambda: True)], interval=0)
    result = buttons.update(0.0)
    assert result.is_up("A")


def test_button_is_down_when_pin_is_low_at_boot():
    buttons = DebouncedButtons([("A", lambda: False)], interval=0)
    result = buttons.update(0.0)
    assert result.is_down("A")


def test_button_is_pressed_on_falling_edge_committed():
    pin = [True]
    buttons = DebouncedButtons([("A", lambda: pin[0])], interval=0)

    pin[0] = False
    result = buttons.update(0.0)

    assert result.is_pressed("A")


def test_button_is_released_on_rising_edge_committed():
    pin = [False]
    buttons = DebouncedButtons([("A", lambda: pin[0])], interval=0)
    buttons.update(0.0)  # settle into DOWN state

    pin[0] = True
    result = buttons.update(0.0)

    assert result.is_released("A")


def test_button_becomes_down_not_pressed_when_held_after_press_edge():
    pin = [True]
    buttons = DebouncedButtons([("A", lambda: pin[0])], interval=0)
    pin[0] = False
    buttons.update(0.0)  # PRESSED

    result = buttons.update(0.1)  # stable low, no pending edge

    assert result.is_down("A")
    assert not result.is_pressed("A")


def test_button_becomes_up_not_released_when_stable_after_release_edge():
    pin = [False]
    buttons = DebouncedButtons([("A", lambda: pin[0])], interval=0)
    buttons.update(0.0)  # DOWN
    pin[0] = True
    buttons.update(0.0)  # RELEASED

    result = buttons.update(0.1)  # stable high, no pending edge

    assert result.is_up("A")
    assert not result.is_released("A")


def test_bounce_before_debounce_interval_does_not_commit_edge():
    pin = [True]
    buttons = DebouncedButtons([("A", lambda: pin[0])], interval=0.1)

    pin[0] = False  # press
    buttons.update(0.05)  # 0.05 < 0.1, no commit yet
    pin[0] = True  # bounce back — resets candidate
    buttons.update(0.03)
    pin[0] = False  # press again
    result = buttons.update(0.03)  # only 0.03 accumulated since last reset

    assert result.is_up("A")


def test_button_is_pressed_when_edge_held_for_full_debounce_interval():
    pin = [True]
    buttons = DebouncedButtons([("A", lambda: pin[0])], interval=0.1)
    pin[0] = False

    buttons.update(0.05)  # 0.05 accumulated, no commit yet
    result = buttons.update(0.06)  # total 0.11 >= 0.1, commits PRESSED

    assert result.is_pressed("A")


def test_button_held_low_at_boot_reads_as_down_not_pressed():
    pin = [False]  # button already held down at power-on
    buttons = DebouncedButtons([("A", lambda: pin[0])], interval=0.1)

    result = buttons.update(0.2)  # elapsed > interval but settled == candidate, no edge

    assert result.is_down("A")
    assert not result.is_pressed("A")


def test_two_buttons_track_their_own_states_independently():
    pin_a = [True]
    pin_b = [False]
    buttons = DebouncedButtons(
        [("A", lambda: pin_a[0]), ("B", lambda: pin_b[0])],
        interval=0,
    )

    pin_a[0] = False  # A pressed; B stays low
    result = buttons.update(0.0)

    assert result.is_pressed("A")
    assert result.is_down("B")
    assert not result.is_pressed("B")

"""Board setup functions for the Adafruit RP2040 PropMaker Feather.

Each function sets up one piece of hardware and returns the configured object
(or ``None`` when the hardware is absent).  Call these at the top of your
``code.py`` before constructing any ``EffectOutput`` or game-engine objects.

Typical usage::

    import hardware.circuitpython.propmaker as propmaker

    i2c = propmaker.setup_i2c()
    matrix = propmaker.setup_matrix_is31fl3741(i2c)
    buttons = propmaker.setup_buttons(board.D9, board.D10, board.D11, board.D12)
    propmaker.setup_external_power()
    accelerometer = propmaker.setup_accelerometer(i2c)  # None if absent
"""

import time

import adafruit_is31fl3741
import board
import busio
import digitalio
from adafruit_is31fl3741.adafruit_rgbmatrixqt import Adafruit_RGBMatrixQT

from hardware.shared.debounced_buttons import DebouncedButtons


def setup_i2c():
    """Return an I2C bus on the board's default SDA/SCL pins."""
    return busio.I2C(board.SCL, board.SDA)


def setup_matrix_is31fl3741(i2c):
    """Return a configured IS31FL3741 driver on *i2c*.

    Retries until the matrix responds (useful if the I2C bus is still
    settling at boot).  Sets LED scaling to 0x33 and global current to 0xFF
    then enables the matrix.
    """
    while True:
        try:
            matrix = Adafruit_RGBMatrixQT(i2c, allocate=adafruit_is31fl3741.MUST_BUFFER)
            break
        except Exception:
            time.sleep(1)
    matrix.set_led_scaling(0x33)
    matrix.global_current = 0xFF
    matrix.enable = True
    return matrix


def setup_buttons(*pins):
    """Return a ``DebouncedButtons`` instance for the given pins with pull-up resistors.

    Button labels are assigned alphabetically by position ("A", "B", …).
    """
    labels = [chr(ord("A") + i) for i in range(len(pins))]
    pairs = []
    for label, pin in zip(labels, pins):
        btn = digitalio.DigitalInOut(pin)
        btn.switch_to_input(pull=digitalio.Pull.UP)
        pairs.append((label, lambda p=btn: p.value))
    return DebouncedButtons(pairs)


def setup_external_power():
    """Enable the PropMaker's EXTERNAL_POWER rail (powers NeoPixels, audio amp, and other
    peripherals)."""
    power = digitalio.DigitalInOut(board.EXTERNAL_POWER)
    power.switch_to_output(value=True)


def setup_accelerometer(i2c):
    """Return a configured LIS3DH accelerometer on *i2c*, or ``None`` if absent.

    Prints a distinct warning depending on the failure mode:
    - ``"accelerometer library not installed"`` when ``adafruit_lis3dh`` cannot
      be imported.
    - ``"accelerometer not found on I2C bus"`` when the library is present but
      the sensor cannot be reached.
    """
    try:
        import adafruit_lis3dh
    except ImportError:
        print("accelerometer library not installed")
        return None
    try:
        return adafruit_lis3dh.LIS3DH_I2C(i2c)
    except Exception:
        print("accelerometer not found on I2C bus")
        return None

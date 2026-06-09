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
    motor = propmaker.setup_drv2605(i2c)  # None if absent
    transmitters, receiver = propmaker.setup_ir(IR_RX_PIN, IR_LINE_PIN)
"""

import time

import adafruit_is31fl3741
import board
import busio
import digitalio
import pulseio
from adafruit_is31fl3741.adafruit_rgbmatrixqt import Adafruit_RGBMatrixQT

from engine.network import AREA_OF_EFFECT, CONE, LINE
from hardware.circuitpython.infrared_io import PulseInReader, PulseOutWriter
from hardware.shared.debounced_buttons import DebouncedButtons
from hardware.shared.ir_protocol import AuraInfraredDecoder, AuraInfraredEncoder
from hardware.shared.ir_transport import InfraredSingleReceiver, InfraredTransmitter


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


def setup_drv2605(i2c):
    """Return a configured DRV2605 haptic motor driver on *i2c*, or ``None`` if absent.

    Prints a distinct warning depending on the failure mode:
    - ``"drv2605 library not installed"`` when ``adafruit_drv2605`` cannot
      be imported.
    - ``"drv2605 not found on I2C bus"`` when the library is present but
      the driver cannot be reached.
    """
    try:
        import adafruit_drv2605
    except ImportError:
        print("drv2605 library not installed")
        return None
    try:
        return adafruit_drv2605.DRV2605(i2c)
    except Exception:
        print("drv2605 not found on I2C bus")
        return None


def setup_ir(
    rx_pin: object,  # pulseio pin — no stub on CPython
    line_pin: object,  # pulseio pin — no stub on CPython
    cone_pin: object | None = None,
    aoe_pin: object | None = None,
) -> tuple[dict[str, InfraredTransmitter], InfraredSingleReceiver]:
    """Set up IR transceiver hardware and return the transmitter map + receiver.

    Constructs a ``pulseio.PulseIn`` for receive and one ``pulseio.PulseOut``
    per wired emitter pin, then wraps them in the hardware-agnostic transport
    objects from :mod:`hardware.shared.ir_transport`.

    The returned ``transmitters`` dict maps emitter constants (``LINE``,
    ``CONE``, ``AREA_OF_EFFECT``) to :class:`~hardware.shared.ir_transport.InfraredTransmitter`
    instances.  Only emitters with a non-``None`` pin are included.

    Pass the returned values directly to :class:`~engine.network.HardwareNetworkControls`
    and poll ``receiver.receive()`` every tick to queue incoming
    :class:`~engine.network.NetworkEvents.IRReceived` events.

    Args:
        rx_pin: CircuitPython pin for the IR receiver (``pulseio.PulseIn``).
        line_pin: CircuitPython pin for the LINE emitter (required, must not be ``None``).
        cone_pin: CircuitPython pin for the CONE emitter, or ``None`` to omit.
        aoe_pin: CircuitPython pin for the AREA_OF_EFFECT emitter, or ``None``.

    Returns:
        A tuple ``(transmitters, receiver)`` where ``transmitters`` is a
        ``dict[str, InfraredTransmitter]`` and ``receiver`` is an
        ``InfraredSingleReceiver``.

    Raises:
        ValueError: If *line_pin* is ``None`` (the LINE emitter is always required).
    """
    if line_pin is None:
        raise ValueError("line_pin is required — the LINE emitter must always be wired")

    pulsein = pulseio.PulseIn(rx_pin, maxlen=256, idle_state=True)
    reader = PulseInReader(pulsein)
    receiver = InfraredSingleReceiver(reader, AuraInfraredDecoder())

    transmitters: dict[str, InfraredTransmitter] = {}
    for emitter, pin in ((LINE, line_pin), (CONE, cone_pin), (AREA_OF_EFFECT, aoe_pin)):
        if pin is None:
            continue
        pulseout = pulseio.PulseOut(pin, frequency=38000, duty_cycle=0x8000)
        writer = PulseOutWriter(pulseout)
        transmitters[emitter] = InfraredTransmitter(writer, AuraInfraredEncoder())

    return transmitters, receiver

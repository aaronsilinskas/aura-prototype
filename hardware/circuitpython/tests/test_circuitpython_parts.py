"""Tests for ``CircuitPythonParts``, the board's ``DeviceParts`` adapter.

Each part is exercised through the adapter's public methods. The CircuitPython
libraries are faked at their public names (``busio.I2C``, ``digitalio.DigitalInOut``,
``neopixel.NeoPixel``, ``Adafruit_RGBMatrixQT``) on the stub modules conftest.py
installs; the board module is a plain namespace of pin objects.
"""

from __future__ import annotations

import sys
import time
from types import SimpleNamespace
from typing import ClassVar

import pytest

from hardware.circuitpython.circuitpython_parts import CircuitPythonParts
from hardware.circuitpython.is31fl3741_output import IS31FL3741EffectOutput
from hardware.shared.device_config import MatrixPixelsConfig, NeoPixelStripConfig
from hardware.shared.device_parts import PinRef


class _Pin:
    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:
        return f"_Pin({self.name!r})"


def _board(*names: str) -> SimpleNamespace:
    return SimpleNamespace(**{name: _Pin(name) for name in names})


class _FakeDigitalInOut:
    """A GPIO: remembers its pin, direction and pull, and holds a settable ``value``."""

    built: ClassVar[list[_FakeDigitalInOut]] = []

    def __init__(self, pin: object) -> None:
        self.pin = pin
        self.direction: str | None = None
        self.pull: object | None = None
        self.value: bool | None = None
        _FakeDigitalInOut.built.append(self)

    def switch_to_output(self, value: bool = False) -> None:
        self.direction = "output"
        self.value = value

    def switch_to_input(self, pull: object | None = None) -> None:
        self.direction = "input"
        self.pull = pull


_PULL_UP = "pull-up"


@pytest.fixture
def gpio(monkeypatch: pytest.MonkeyPatch) -> list[_FakeDigitalInOut]:
    """Fake ``digitalio``; returns every GPIO built, in order."""
    _FakeDigitalInOut.built = []
    digitalio = sys.modules["digitalio"]
    monkeypatch.setattr(digitalio, "DigitalInOut", _FakeDigitalInOut, raising=False)
    monkeypatch.setattr(digitalio, "Pull", SimpleNamespace(UP=_PULL_UP), raising=False)
    return _FakeDigitalInOut.built


# ---------------------------------------------------------------------------
# Pin references
# ---------------------------------------------------------------------------


def test_unknown_pin_name_raises_value_error_naming_the_config_field(
    gpio: list[_FakeDigitalInOut],
) -> None:
    parts = CircuitPythonParts(_board("GP28"))

    expected = r"^high_current_rail\.pin: pin 'GP99' not found on board$"
    with pytest.raises(ValueError, match=expected):
        parts.high_current_rail(PinRef("GP99", "high_current_rail.pin"), True)


# ---------------------------------------------------------------------------
# High-current rail
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("level", [True, False])
def test_rail_drives_its_pin_to_the_level_it_is_told(
    gpio: list[_FakeDigitalInOut], level: bool
) -> None:
    board = _board("GP28")
    parts = CircuitPythonParts(board)

    parts.high_current_rail(PinRef("GP28", "high_current_rail.pin"), level)

    assert [(g.pin, g.direction, g.value) for g in gpio] == [(board.GP28, "output", level)]


# ---------------------------------------------------------------------------
# Buses
# ---------------------------------------------------------------------------


class _FakeI2C:
    """An I2C bus on ``(scl, sda)``; raises as ``busio.I2C`` does when nothing pulls it up."""

    pulled_up = True

    def __init__(self, scl: object, sda: object) -> None:
        if not _FakeI2C.pulled_up:
            raise RuntimeError("No pull up found on SDA or SCL; check your wiring")
        self.pins = (scl, sda)


class _FakeSPI:
    def __init__(self, sck: object, MOSI: object = None, MISO: object = None) -> None:  # noqa: N803
        self.pins = (sck, MOSI, MISO)


@pytest.fixture
def buses(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fake ``busio`` with a pulled-up I2C bus."""
    _FakeI2C.pulled_up = True
    busio = sys.modules["busio"]
    monkeypatch.setattr(busio, "I2C", _FakeI2C, raising=False)
    monkeypatch.setattr(busio, "SPI", _FakeSPI, raising=False)


def test_i2c_bus_is_built_on_the_declared_pins(buses: None) -> None:
    board = _board("GP5", "GP4")
    parts = CircuitPythonParts(board)

    bus = parts.i2c_bus(PinRef("GP5", "i2c.scl"), PinRef("GP4", "i2c.sda"))

    assert isinstance(bus, _FakeI2C)
    assert bus.pins == (board.GP5, board.GP4)


def test_i2c_bus_is_built_on_the_board_default_pins_when_none_are_declared(buses: None) -> None:
    board = _board("SCL", "SDA")
    parts = CircuitPythonParts(board)

    bus = parts.i2c_bus(None, None)

    assert isinstance(bus, _FakeI2C)
    assert bus.pins == (board.SCL, board.SDA)


def test_i2c_bus_reports_no_bus_when_nothing_pulls_it_up(buses: None) -> None:
    _FakeI2C.pulled_up = False
    parts = CircuitPythonParts(_board("SCL", "SDA"))

    assert parts.i2c_bus(None, None) is None


def test_i2c_bus_is_the_injected_bus_when_one_is_held(buses: None) -> None:
    injected = object()
    parts = CircuitPythonParts(_board("GP5", "GP4"), i2c=injected)

    assert parts.i2c_bus(PinRef("GP5", "i2c.scl"), PinRef("GP4", "i2c.sda")) is injected


def test_spi_bus_is_built_on_the_declared_pins(buses: None) -> None:
    board = _board("GP18", "GP19", "GP16")
    parts = CircuitPythonParts(board)

    bus = parts.spi_bus(
        PinRef("GP18", "spi.sck"), PinRef("GP19", "spi.mosi"), PinRef("GP16", "spi.miso")
    )

    assert isinstance(bus, _FakeSPI)
    assert bus.pins == (board.GP18, board.GP19, board.GP16)


def test_spi_bus_is_the_board_default_bus_when_no_pins_are_declared(buses: None) -> None:
    default_bus = object()
    board = SimpleNamespace(SPI=lambda: default_bus)
    parts = CircuitPythonParts(board)

    assert parts.spi_bus(None, None, None) is default_bus


# ---------------------------------------------------------------------------
# Button pin readers
# ---------------------------------------------------------------------------


def test_button_reader_configures_its_pin_as_a_pulled_up_input(
    gpio: list[_FakeDigitalInOut],
) -> None:
    board = _board("D9")
    parts = CircuitPythonParts(board)

    parts.button_reader(PinRef("D9", "buttons[0]"))

    assert [(g.pin, g.direction, g.pull) for g in gpio] == [(board.D9, "input", _PULL_UP)]


def test_button_reader_reads_the_pins_current_raw_level(gpio: list[_FakeDigitalInOut]) -> None:
    parts = CircuitPythonParts(_board("D9"))
    read = parts.button_reader(PinRef("D9", "buttons[0]"))
    (pin,) = gpio

    pin.value = True
    released = read()
    pin.value = False
    pressed = read()

    assert (released, pressed) == (True, False)


# ---------------------------------------------------------------------------
# NeoPixel strips
# ---------------------------------------------------------------------------


class _FakeNeoPixel(list):
    """A strip's pixel list, remembering how it was constructed."""

    def __init__(
        self, pin: object, n: int, *, pixel_order: str, brightness: float, auto_write: bool
    ) -> None:
        super().__init__([0] * n)
        self.pin = pin
        self.pixel_order = pixel_order
        self.brightness = brightness
        self.auto_write = auto_write


@pytest.fixture
def neopixel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys.modules["neopixel"], "NeoPixel", _FakeNeoPixel, raising=False)


def _strip(scope_pixels: dict[str, range]) -> NeoPixelStripConfig:
    count = max(r.stop for r in scope_pixels.values())
    return NeoPixelStripConfig("D5", count, "GRB", 0.25, scope_pixels)


def test_neopixel_strip_drives_a_strip_on_its_pin_with_its_count_order_and_brightness(
    neopixel: None,
) -> None:
    board = _board("D5")
    parts = CircuitPythonParts(board)

    output = parts.neopixel_strip(_strip({"personal": range(0, 10)}), PinRef("D5", "pixels.pin"))

    strip = output.strip
    assert isinstance(strip, _FakeNeoPixel)
    assert (strip.pin, len(strip), strip.pixel_order, strip.brightness, strip.auto_write) == (
        board.D5,
        10,
        "GRB",
        0.25,
        False,
    )


def test_neopixel_strip_writes_each_scope_into_its_own_segment(neopixel: None) -> None:
    parts = CircuitPythonParts(_board("D5"))
    output = parts.neopixel_strip(
        _strip({"personal": range(0, 2), "ambient": range(2, 4)}), PinRef("D5", "pixels.pin")
    )
    buffer = output.create_buffer("ambient")
    buffer[0], buffer[1] = 0x112233, 0x445566

    output.update_pixels("ambient", buffer)

    strip = output.strip
    assert isinstance(strip, _FakeNeoPixel)
    assert list(strip) == [0, 0, 0x112233, 0x445566]


# ---------------------------------------------------------------------------
# Matrix pixels
# ---------------------------------------------------------------------------


class _FakeMatrixDriver:
    """An IS31FL3741 driver; the first ``unresponsive_attempts`` constructions raise."""

    unresponsive_attempts = 0

    def __init__(self, i2c: object, **kwargs: object) -> None:
        if _FakeMatrixDriver.unresponsive_attempts > 0:
            _FakeMatrixDriver.unresponsive_attempts -= 1
            raise OSError("no ACK")
        self.i2c = i2c
        self.kwargs = kwargs
        self.led_scaling: int | None = None
        self.global_current = 0
        self.enable = False

    def set_led_scaling(self, scaling: int) -> None:
        self.led_scaling = scaling


class _Clock:
    """``time.monotonic``, advanced only by ``time.sleep``."""

    def __init__(self) -> None:
        self.now = 0.0

    def sleep(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def matrix_driver(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeMatrixDriver.unresponsive_attempts = 0
    module = sys.modules["adafruit_is31fl3741.adafruit_rgbmatrixqt"]
    monkeypatch.setattr(module, "Adafruit_RGBMatrixQT", _FakeMatrixDriver)
    clock = _Clock()
    monkeypatch.setattr(time, "monotonic", lambda: clock.now)
    monkeypatch.setattr(time, "sleep", clock.sleep)


def _matrix(brightness: float = 1.0, address: int | None = None) -> MatrixPixelsConfig:
    return MatrixPixelsConfig(13, {"personal": range(0, 9)}, brightness=brightness, address=address)


def _driver(output: IS31FL3741EffectOutput) -> _FakeMatrixDriver:
    driver = output.matrix
    assert isinstance(driver, _FakeMatrixDriver)
    return driver


def test_matrix_pixels_drive_a_matrix_on_the_given_bus_at_its_configured_address(
    matrix_driver: None,
) -> None:
    bus = object()
    output = CircuitPythonParts(_board()).matrix_pixels(_matrix(address=0x31), bus)

    driver = _driver(output)
    assert (driver.i2c, driver.kwargs["address"]) == (bus, 0x31)


def test_matrix_pixels_leave_the_drivers_default_address_when_none_is_configured(
    matrix_driver: None,
) -> None:
    output = CircuitPythonParts(_board()).matrix_pixels(_matrix(address=None), object())

    assert "address" not in _driver(output).kwargs


def test_matrix_pixels_are_as_wide_as_the_configured_columns(matrix_driver: None) -> None:
    output = CircuitPythonParts(_board()).matrix_pixels(_matrix(), object())

    assert output.min_resolution == 13


def test_matrix_led_scaling_follows_the_configured_brightness(matrix_driver: None) -> None:
    output = CircuitPythonParts(_board()).matrix_pixels(_matrix(brightness=0.2), object())

    assert _driver(output).led_scaling == 0x33  # 0.2 * 0xFF


def test_matrix_starts_enabled_at_full_global_current(matrix_driver: None) -> None:
    output = CircuitPythonParts(_board()).matrix_pixels(_matrix(), object())

    driver = _driver(output)
    assert (driver.global_current, driver.enable) == (0xFF, True)


def test_matrix_that_responds_within_the_startup_window_is_used(matrix_driver: None) -> None:
    _FakeMatrixDriver.unresponsive_attempts = 2

    output = CircuitPythonParts(_board()).matrix_pixels(_matrix(), object())

    assert isinstance(output.matrix, _FakeMatrixDriver)


def test_matrix_that_never_responds_raises_after_the_startup_window(matrix_driver: None) -> None:
    _FakeMatrixDriver.unresponsive_attempts = 1000
    parts = CircuitPythonParts(_board())

    with pytest.raises(RuntimeError, match="IS31FL3741 matrix did not respond within 3s"):
        parts.matrix_pixels(_matrix(), object())

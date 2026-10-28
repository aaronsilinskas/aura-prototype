"""Tests for ``CircuitPythonParts``, the board's ``DeviceParts`` adapter.

Each part is exercised through the adapter's public methods. The CircuitPython
libraries are faked at their public names (``busio.I2C``, ``digitalio.DigitalInOut``,
``neopixel.NeoPixel``, ``Adafruit_RGBMatrixQT``) on the stub modules conftest.py
installs; the board module is a plain namespace of pin objects.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import ClassVar

import pytest

from effects.effect import AudioPlaybackConfig, Effect, EffectAudio, EffectHaptic, HapticPattern
from engine.audio import AudioRegistry
from engine.effects.output import EffectOutput
from engine.events import EffectEvent
from engine.state import EffectReceipt
from hardware.circuitpython.circuitpython_parts import CircuitPythonParts, SdCardMountError
from hardware.circuitpython.is31fl3741_output import IS31FL3741EffectOutput
from hardware.shared.device_config import (
    AudioConfig,
    I2CDeviceConfig,
    MatrixPixelsConfig,
    NeoPixelStripConfig,
    RadioConfig,
    SDCardConfig,
)
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
# Board name
# ---------------------------------------------------------------------------


def test_board_name_is_the_running_boards_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys.modules["board"], "board_id", "pimoroni_pico_plus2w", raising=False)

    assert CircuitPythonParts(_board()).board_name() == "pimoroni_pico_plus2w"


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


def test_i2c_bus_is_the_injected_bus_when_one_is_held(
    buses: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    built: list[object] = []
    monkeypatch.setattr(sys.modules["busio"], "I2C", lambda *pins: built.append(pins))
    injected = object()
    parts = CircuitPythonParts(_board("GP5", "GP4"), i2c=injected)

    assert parts.i2c_bus(PinRef("GP5", "i2c.scl"), PinRef("GP4", "i2c.sda")) is injected
    assert built == []  # a built-then-discarded bus would still claim its pins


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


def test_neopixel_strip_pin_naming_an_unknown_pin_raises_value_error_naming_its_field(
    neopixel: None,
) -> None:
    parts = CircuitPythonParts(_board("D5"))

    expected = r"^pixels\.scopes\.personal\.pin: pin 'GP99' not found on board$"
    with pytest.raises(ValueError, match=expected):
        parts.neopixel_strip(
            _strip({"personal": range(0, 4)}), PinRef("GP99", "pixels.scopes.personal.pin")
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
    responded: _FakeMatrixDriver | None = None
    """The driver that answered, once one has."""

    def __init__(self, i2c: object, **kwargs: object) -> None:
        if _FakeMatrixDriver.unresponsive_attempts > 0:
            _FakeMatrixDriver.unresponsive_attempts -= 1
            raise OSError("no ACK")
        _FakeMatrixDriver.responded = self
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
    _FakeMatrixDriver.responded = None
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


@pytest.mark.parametrize(("brightness", "scaling"), [(0.2, 0x33), (1.0, 0xFF)])
def test_matrix_led_scaling_follows_the_configured_brightness(
    matrix_driver: None, brightness: float, scaling: int
) -> None:
    output = CircuitPythonParts(_board()).matrix_pixels(_matrix(brightness=brightness), object())

    assert _driver(output).led_scaling == scaling


@pytest.mark.parametrize("address", [None, 0x31])
def test_matrix_driver_buffers_pixel_writes_until_show(
    matrix_driver: None, address: int | None
) -> None:
    output = CircuitPythonParts(_board()).matrix_pixels(_matrix(address=address), object())

    assert _driver(output).kwargs["allocate"] == sys.modules["adafruit_is31fl3741"].MUST_BUFFER


def test_matrix_starts_enabled_at_full_global_current(matrix_driver: None) -> None:
    output = CircuitPythonParts(_board()).matrix_pixels(_matrix(), object())

    driver = _driver(output)
    assert (driver.global_current, driver.enable) == (0xFF, True)


def test_matrix_that_responds_within_the_startup_window_is_used(matrix_driver: None) -> None:
    _FakeMatrixDriver.unresponsive_attempts = 2

    output = CircuitPythonParts(_board()).matrix_pixels(_matrix(), object())

    assert output.matrix is _FakeMatrixDriver.responded


def test_matrix_that_never_responds_raises_after_the_startup_window(matrix_driver: None) -> None:
    _FakeMatrixDriver.unresponsive_attempts = 1000
    parts = CircuitPythonParts(_board())

    with pytest.raises(RuntimeError, match="IS31FL3741 matrix did not respond within 3s"):
        parts.matrix_pixels(_matrix(), object())


# ---------------------------------------------------------------------------
# I2C sensors and haptics
# ---------------------------------------------------------------------------


class _FakeI2CChip:
    """An I2C chip driver, remembering the bus and keywords it was built with."""

    def __init__(self, i2c: object, **kwargs: object) -> None:
        self.i2c = i2c
        self.kwargs = kwargs


def _install_library(
    monkeypatch: pytest.MonkeyPatch, name: str, **attributes: object
) -> ModuleType:
    """Install a fake driver library at *name* for the duration of a test."""
    module = ModuleType(name)
    for attribute, value in attributes.items():
        setattr(module, attribute, value)
    monkeypatch.setitem(sys.modules, name, module)
    return module


@pytest.fixture
def lis3dh(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_library(monkeypatch, "adafruit_lis3dh", LIS3DH_I2C=_FakeI2CChip)


def test_accelerometer_is_a_lis3dh_on_the_given_bus_at_its_configured_address(
    lis3dh: None,
) -> None:
    bus = object()

    accelerometer = CircuitPythonParts(_board()).accelerometer(I2CDeviceConfig(address=0x19), bus)

    assert isinstance(accelerometer, _FakeI2CChip)
    assert (accelerometer.i2c, accelerometer.kwargs) == (bus, {"address": 0x19})


def test_accelerometer_leaves_the_drivers_default_address_when_none_is_configured(
    lis3dh: None,
) -> None:
    accelerometer = CircuitPythonParts(_board()).accelerometer(I2CDeviceConfig(), object())

    assert isinstance(accelerometer, _FakeI2CChip)
    assert accelerometer.kwargs == {}


# The all-zero-register reading a dead MMC5603 that still ACKs the bus streams;
# the on-device literal, not the module's constant.
_DEAD_MAGNETOMETER_UT = (-3276.8, -3276.8, -3276.8)
_LIVE_MAGNETOMETER_UT = (12.3, -4.5, 40.1)


class _FakeMmc5603(_FakeI2CChip):
    """An MMC5603 whose first ``dead_polls`` reads of ``.magnetic`` are the dead-chip reading."""

    dead_polls = 0

    def __init__(self, i2c: object, **kwargs: object) -> None:
        super().__init__(i2c, **kwargs)
        self.data_rate: int | None = None
        self.continuous_mode = False
        self.polls = 0

    @property
    def magnetic(self) -> tuple[float, float, float]:
        self.polls += 1
        if self.polls <= _FakeMmc5603.dead_polls:
            return _DEAD_MAGNETOMETER_UT
        return _LIVE_MAGNETOMETER_UT


@pytest.fixture
def mmc56x3(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeMmc5603.dead_polls = 0
    _install_library(monkeypatch, "adafruit_mmc56x3", MMC5603=_FakeMmc5603)
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)


def _magnetometer() -> _FakeMmc5603:
    magnetometer = CircuitPythonParts(_board()).magnetometer(I2CDeviceConfig(), object())
    assert isinstance(magnetometer, _FakeMmc5603)
    return magnetometer


def test_magnetometer_is_an_mmc5603_on_the_given_bus_at_its_configured_address(
    mmc56x3: None,
) -> None:
    bus = object()

    magnetometer = CircuitPythonParts(_board()).magnetometer(I2CDeviceConfig(address=0x32), bus)

    assert isinstance(magnetometer, _FakeMmc5603)
    assert (magnetometer.i2c, magnetometer.kwargs) == (bus, {"address": 0x32})


def test_magnetometer_leaves_the_drivers_default_address_when_none_is_configured(
    mmc56x3: None,
) -> None:
    assert _magnetometer().kwargs == {}


def test_magnetometer_free_runs_in_continuous_mode_at_100hz(mmc56x3: None) -> None:
    magnetometer = _magnetometer()

    assert (magnetometer.data_rate, magnetometer.continuous_mode) == (100, True)


def test_magnetometer_that_reads_dead_on_every_axis_raises_a_wiring_fault(mmc56x3: None) -> None:
    _FakeMmc5603.dead_polls = 1000

    with pytest.raises(RuntimeError, match="check its power and ground wiring"):
        _magnetometer()


def test_magnetometer_whose_first_conversions_read_dead_is_used_once_one_reads_live(
    mmc56x3: None,
) -> None:
    _FakeMmc5603.dead_polls = 2

    assert _magnetometer().magnetic == _LIVE_MAGNETOMETER_UT


class _FakeDrv2605(_FakeI2CChip):
    """A DRV2605 haptic driver; counts how often it was told to play."""

    built: ClassVar[list[_FakeDrv2605]] = []

    def __init__(self, i2c: object, **kwargs: object) -> None:
        super().__init__(i2c, **kwargs)
        self.sequence: list[object] = [None] * 8
        self.plays = 0
        _FakeDrv2605.built.append(self)

    def play(self) -> None:
        self.plays += 1


@pytest.fixture
def drv2605(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeDrv2605.built = []
    monkeypatch.setattr(sys.modules["adafruit_drv2605"], "DRV2605", _FakeDrv2605, raising=False)


def _buzz(output: EffectOutput) -> None:
    effect = Effect(
        name="buzz",
        haptic=EffectHaptic(patterns={"start": HapticPattern([HapticPattern.STRONG_BUZZ])}),
    )
    output.handle_event(
        EffectEvent("buzz", "haptic", "start"), frozenset({"all"}), effect, EffectReceipt(1)
    )


def test_haptic_output_drives_a_drv2605_on_the_given_bus_at_its_configured_address(
    drv2605: None,
) -> None:
    bus = object()

    CircuitPythonParts(_board()).haptic_output(I2CDeviceConfig(address=0x5B), bus)

    assert [(d.i2c, d.kwargs) for d in _FakeDrv2605.built] == [(bus, {"address": 0x5B})]


def test_haptic_output_plays_haptic_effects_on_its_drv2605(drv2605: None) -> None:
    output = CircuitPythonParts(_board()).haptic_output(I2CDeviceConfig(), object())

    _buzz(output)

    assert [d.plays for d in _FakeDrv2605.built] == [1]


def test_haptic_output_leaves_the_drivers_default_address_when_none_is_configured(
    drv2605: None,
) -> None:
    CircuitPythonParts(_board()).haptic_output(I2CDeviceConfig(), object())

    assert [d.kwargs for d in _FakeDrv2605.built] == [{}]


# ---------------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------------


class _FakeVoice:
    def __init__(self) -> None:
        self.level = 0.0
        self.playing = False
        self.wave: _FakeWaveFile | None = None

    def play(self, wave: _FakeWaveFile, loop: bool = False) -> None:
        self.wave = wave
        self.playing = True

    def stop(self) -> None:
        self.playing = False


class _FakeMixer:
    def __init__(self, *, voice_count: int, **_format: object) -> None:
        self.voice = [_FakeVoice() for _ in range(voice_count)]


class _FakeI2SOut:
    """An I2S amp on its three pins, remembering the mixer it plays."""

    built: ClassVar[list[_FakeI2SOut]] = []

    def __init__(self, bit_clock: object, word_select: object, data: object) -> None:
        self.pins = (bit_clock, word_select, data)
        self.mixer: _FakeMixer | None = None
        _FakeI2SOut.built.append(self)

    def play(self, mixer: _FakeMixer) -> None:
        self.mixer = mixer


class _FakeWaveFile:
    def __init__(self, file: object) -> None:
        self.path = getattr(file, "name", None)


@pytest.fixture
def audio_stack(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeI2SOut.built = []
    monkeypatch.setattr(sys.modules["audiobusio"], "I2SOut", _FakeI2SOut, raising=False)
    monkeypatch.setattr(sys.modules["audiomixer"], "Mixer", _FakeMixer, raising=False)
    monkeypatch.setattr(sys.modules["audiocore"], "WaveFile", _FakeWaveFile, raising=False)


_I2S_PINS = (
    PinRef("GP10", "audio.i2s_bit_clock"),
    PinRef("GP11", "audio.i2s_word_select"),
    PinRef("GP12", "audio.i2s_data"),
)


def _audio(voices: int = 2, max_volume: float = 0.5) -> AudioConfig:
    return AudioConfig(voices, max_volume, "GP10", "GP11", "GP12")


def _amp() -> _FakeI2SOut:
    (amp,) = _FakeI2SOut.built
    return amp


def _mixer() -> _FakeMixer:
    mixer = _amp().mixer
    assert mixer is not None
    return mixer


def test_audio_output_plays_through_an_i2s_amp_on_the_referenced_pins(audio_stack: None) -> None:
    board = _board("GP10", "GP11", "GP12")

    CircuitPythonParts(board).audio_output(_audio(), AudioRegistry(), *_I2S_PINS)

    assert _amp().pins == (board.GP10, board.GP11, board.GP12)


def test_audio_output_mixes_as_many_voices_as_configured(audio_stack: None) -> None:
    CircuitPythonParts(_board("GP10", "GP11", "GP12")).audio_output(
        _audio(voices=3), AudioRegistry(), *_I2S_PINS
    )

    assert len(_mixer().voice) == 3


def test_audio_output_caps_full_loudness_at_the_configured_max_volume(audio_stack: None) -> None:
    output = CircuitPythonParts(_board("GP10", "GP11", "GP12")).audio_output(
        _audio(max_volume=0.25), AudioRegistry(), *_I2S_PINS
    )

    output.set_loudness(0, 1.0)

    assert _mixer().voice[0].level == 0.25


def test_audio_output_resolves_clip_names_through_the_given_registry(
    audio_stack: None, tmp_path: Path
) -> None:
    clip = tmp_path / "zap.wav"
    clip.write_bytes(b"RIFF")
    registry = AudioRegistry()
    registry.set_scene_sounds({"zap": str(clip)})
    output = CircuitPythonParts(_board("GP10", "GP11", "GP12")).audio_output(
        _audio(), registry, *_I2S_PINS
    )
    effect = Effect(
        name="zap",
        audio=EffectAudio(clips={"start": AudioPlaybackConfig(name="scene.zap", loop=False)}),
    )

    output.handle_event(
        EffectEvent("zap", "audio", "start"), frozenset({"all"}), effect, EffectReceipt(1)
    )

    assert [v.wave.path for v in _mixer().voice if v.playing and v.wave] == [str(clip)]


@pytest.mark.parametrize("unknown", range(3))
def test_audio_pin_naming_an_unknown_pin_raises_value_error_naming_its_field(
    audio_stack: None, unknown: int
) -> None:
    pins = list(_I2S_PINS)
    field = pins[unknown].field
    pins[unknown] = PinRef("GP99", field)
    parts = CircuitPythonParts(_board("GP10", "GP11", "GP12"))

    with pytest.raises(ValueError, match=rf"^{field}: pin 'GP99' not found on board$"):
        parts.audio_output(_audio(), AudioRegistry(), *pins)


# ---------------------------------------------------------------------------
# IR pulse readers
# ---------------------------------------------------------------------------


class _FakePulseIn(list):
    """A ``pulseio.PulseIn`` buffer of pulse durations, remembering how it was opened."""

    built: ClassVar[list[_FakePulseIn]] = []

    def __init__(self, pin: object, *, maxlen: int, idle_state: bool) -> None:
        super().__init__()
        self.pin = pin
        self.maxlen = maxlen
        self.idle_state = idle_state
        _FakePulseIn.built.append(self)

    def popleft(self) -> int:
        return self.pop(0)


@pytest.fixture
def pulsein(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakePulseIn.built = []
    monkeypatch.setattr(sys.modules["pulseio"], "PulseIn", _FakePulseIn, raising=False)


def test_ir_reader_reads_pulses_received_on_its_pin(pulsein: None) -> None:
    board = _board("GP7")

    reader = CircuitPythonParts(board).ir_reader(PinRef("GP7", "ir.rx"))
    (pulses,) = _FakePulseIn.built
    pulses.extend([9000, 4500])

    received = [reader.read_pulse() for _ in range(3)]

    assert (pulses.pin, received) == (board.GP7, [9000, 4500, None])


def test_ir_reader_listens_for_an_idle_high_receiver_with_a_256_pulse_buffer(
    pulsein: None,
) -> None:
    CircuitPythonParts(_board("GP7")).ir_reader(PinRef("GP7", "ir.rx"))

    assert [(p.idle_state, p.maxlen) for p in _FakePulseIn.built] == [(True, 256)]


def test_ir_reader_pin_naming_an_unknown_pin_raises_value_error_naming_its_field(
    pulsein: None,
) -> None:
    parts = CircuitPythonParts(_board("GP7"))

    with pytest.raises(ValueError, match=r"^ir\.rx\[1\]: pin 'GP99' not found on board$"):
        parts.ir_reader(PinRef("GP99", "ir.rx[1]"))


# ---------------------------------------------------------------------------
# IR pulse writers
# ---------------------------------------------------------------------------


class _FakePulseOut:
    """A ``pulseio.PulseOut`` carrier on a pin, recording every pulse train sent."""

    built: ClassVar[list[_FakePulseOut]] = []

    def __init__(self, pin: object, *, frequency: int, duty_cycle: int) -> None:
        self.pin = pin
        self.frequency = frequency
        self.duty_cycle = duty_cycle
        self.sent: list[list[int]] = []
        _FakePulseOut.built.append(self)

    def send(self, durations: list[int]) -> None:
        self.sent.append(list(durations))


class _FakeStateMachine:
    """An ``rp2pio.StateMachine``; program and frequency are positional-only, as on the board."""

    built: ClassVar[list[_FakeStateMachine]] = []

    def __init__(
        self, program: object, frequency: int, /, *, first_set_pin: object, **_kwargs: object
    ) -> None:
        self.pin = first_set_pin
        self.writing = False
        self.written: list[object] = []
        _FakeStateMachine.built.append(self)

    def background_write(self, buffer: object) -> None:
        self.written.append(buffer)


@pytest.fixture
def pulseout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fake ``pulseio.PulseOut`` on silicon without PIO (``rp2pio`` unimportable)."""
    _FakePulseOut.built = []
    monkeypatch.setattr(sys.modules["pulseio"], "PulseOut", _FakePulseOut, raising=False)
    monkeypatch.setitem(sys.modules, "rp2pio", None)


@pytest.fixture
def pio(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fake ``rp2pio`` and ``adafruit_pioasm``, as on RP2040/RP2350 silicon."""
    _FakeStateMachine.built = []
    _install_library(monkeypatch, "rp2pio", StateMachine=_FakeStateMachine)
    program = lambda source: SimpleNamespace(assembled=source)  # noqa: E731
    _install_library(monkeypatch, "adafruit_pioasm", Program=program)


def test_ir_writer_on_silicon_without_pio_reports_the_pulseio_kind(pulseout: None) -> None:
    _writer, kind = CircuitPythonParts(_board("GP8")).ir_writer("line", PinRef("GP8", "ir.line"))

    assert kind == "pulseio"


def test_ir_writer_on_silicon_without_pio_sends_pulses_on_a_38khz_carrier_on_its_pin(
    pulseout: None,
) -> None:
    board = _board("GP8")
    writer, _kind = CircuitPythonParts(board).ir_writer("line", PinRef("GP8", "ir.line"))

    writer.write_pulses([9000, 4500, 560])

    assert [(p.pin, p.frequency, p.sent) for p in _FakePulseOut.built] == [
        (board.GP8, 38000, [[9000, 4500, 560]])
    ]


def test_ir_writer_on_pio_silicon_reports_the_pio_kind(pio: None) -> None:
    _writer, kind = CircuitPythonParts(_board("GP8")).ir_writer("line", PinRef("GP8", "ir.line"))

    assert kind == "pio"


def test_ir_writer_on_pio_silicon_clocks_its_carrier_out_of_a_state_machine_on_its_pin(
    pio: None,
) -> None:
    board = _board("GP8")

    CircuitPythonParts(board).ir_writer("line", PinRef("GP8", "ir.line"))

    assert [sm.pin for sm in _FakeStateMachine.built] == [board.GP8]


def test_ir_writer_on_pio_silicon_sends_pulses_through_its_state_machine(pio: None) -> None:
    writer, _kind = CircuitPythonParts(_board("GP8")).ir_writer("line", PinRef("GP8", "ir.line"))

    writer.write_pulses([9000, 4500, 560])

    ((state_machine),) = _FakeStateMachine.built
    assert len(state_machine.written) == 1


def test_each_ir_writer_on_pio_silicon_gets_its_own_state_machine(pio: None) -> None:
    board = _board("GP8", "GP9", "GP10")
    parts = CircuitPythonParts(board)

    for emitter, pin in (("line", "GP8"), ("cone", "GP9"), ("area_of_effect", "GP10")):
        parts.ir_writer(emitter, PinRef(pin, f"ir.{emitter}"))

    assert [sm.pin for sm in _FakeStateMachine.built] == [board.GP8, board.GP9, board.GP10]


def test_ir_writer_pin_naming_an_unknown_pin_raises_value_error_naming_its_field(
    pulseout: None,
) -> None:
    parts = CircuitPythonParts(_board("GP8"))

    with pytest.raises(ValueError, match=r"^ir\.cone: pin 'GP99' not found on board$"):
        parts.ir_writer("cone", PinRef("GP99", "ir.cone"))


# ---------------------------------------------------------------------------
# Radio transport
# ---------------------------------------------------------------------------


class _FakeRfm69:
    """An ``adafruit_rfm69.RFM69`` chip, remembering how it was built and what it sent."""

    built: ClassVar[list[_FakeRfm69]] = []

    def __init__(self, spi: object, cs: object, reset: object, frequency: float) -> None:
        self.spi = spi
        self.cs = cs
        self.reset = reset
        self.frequency = frequency
        self.node: int | None = None
        self.receive_timeout: float | None = 0.5
        self.sent: list[bytes] = []
        _FakeRfm69.built.append(self)

    def send(self, data: bytes, keep_listening: bool = False) -> None:
        self.sent.append(data)


@pytest.fixture
def rfm69(monkeypatch: pytest.MonkeyPatch, gpio: list[_FakeDigitalInOut]) -> None:
    _FakeRfm69.built = []
    monkeypatch.setattr(sys.modules["adafruit_rfm69"], "RFM69", _FakeRfm69, raising=False)


_RADIO_PINS = (PinRef("D10", "radio.cs"), PinRef("D11", "radio.reset"))


def test_radio_transport_sends_through_an_rfm69_on_the_given_bus_at_its_frequency_and_node(
    rfm69: None,
) -> None:
    bus = object()
    transport = CircuitPythonParts(_board("D10", "D11")).radio_transport(
        RadioConfig("D10", "D11", 433.0, 7), bus, *_RADIO_PINS
    )

    transport.send(b"hi")

    assert [(r.spi, r.frequency, r.node, r.sent) for r in _FakeRfm69.built] == [
        (bus, 433.0, 7, [b"hi"])
    ]


def test_radio_chip_select_and_reset_are_gpios_on_their_referenced_pins(
    rfm69: None, gpio: list[_FakeDigitalInOut]
) -> None:
    board = _board("D10", "D11")

    CircuitPythonParts(board).radio_transport(
        RadioConfig("D10", "D11", 433.0, 7), object(), *_RADIO_PINS
    )

    (chip,) = _FakeRfm69.built
    assert (chip.cs, chip.reset) == tuple(gpio)
    assert [g.pin for g in gpio] == [board.D10, board.D11]


@pytest.mark.parametrize("unknown", range(2))
def test_radio_pin_naming_an_unknown_pin_raises_value_error_naming_its_field(
    rfm69: None, unknown: int
) -> None:
    pins = list(_RADIO_PINS)
    field = pins[unknown].field
    pins[unknown] = PinRef("NOPE", field)

    with pytest.raises(ValueError, match=rf"^{field}: pin 'NOPE' not found on board$"):
        CircuitPythonParts(_board("D10", "D11")).radio_transport(
            RadioConfig("D10", "D11", 433.0, 7), object(), *pins
        )


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


class _FakeSDCard:
    """An ``sdcardio.SDCard``; raises as the real one does when no card is fitted."""

    fitted = True

    def __init__(self, spi: object, cs: object) -> None:
        if not _FakeSDCard.fitted:
            raise OSError("no SD card")
        self.spi = spi
        self.cs = cs


class _FakeVfsFat:
    """A FAT filesystem on a card; raises as the real one does when the card has none."""

    formatted = True

    def __init__(self, card: _FakeSDCard) -> None:
        if not _FakeVfsFat.formatted:
            raise OSError("no FAT filesystem")
        self.card = card


@pytest.fixture
def sd(monkeypatch: pytest.MonkeyPatch) -> list[tuple[_FakeVfsFat, str]]:
    """Fake ``sdcardio`` and ``storage``; returns every ``(filesystem, mount point)`` mounted."""
    _FakeSDCard.fitted = True
    _FakeVfsFat.formatted = True
    mounted: list[tuple[_FakeVfsFat, str]] = []
    monkeypatch.setattr(sys.modules["sdcardio"], "SDCard", _FakeSDCard, raising=False)
    storage = sys.modules["storage"]
    monkeypatch.setattr(storage, "VfsFat", _FakeVfsFat, raising=False)
    monkeypatch.setattr(
        storage,
        "mount",
        lambda fs, mount, readonly=True: mounted.append((fs, mount)),
        raising=False,
    )
    return mounted


def test_storage_mounts_the_card_on_the_given_bus_and_chip_select_at_its_mount_point(
    sd: list[tuple[_FakeVfsFat, str]],
) -> None:
    board = _board("D24")
    bus = object()

    CircuitPythonParts(board).storage(SDCardConfig("D24", "/sd"), bus, PinRef("D24", "sdcard.cs"))

    assert [(fs.card.spi, fs.card.cs, mount) for fs, mount in sd] == [(bus, board.D24, "/sd")]


@pytest.mark.parametrize(
    ("fake", "flag"),
    [(_FakeSDCard, "fitted"), (_FakeVfsFat, "formatted")],
    ids=["absent", "unformatted"],
)
def test_storage_whose_card_fails_to_mount_raises_sd_card_mount_error_naming_cs_and_mount(
    sd: list[tuple[_FakeVfsFat, str]], fake: type, flag: str
) -> None:
    setattr(fake, flag, False)
    parts = CircuitPythonParts(_board("D24"))

    expected = r"^sdcard section is declared but the card at cs=D24 mount=/media failed to mount: "
    with pytest.raises(SdCardMountError, match=expected) as raised:
        parts.storage(SDCardConfig("D24", "/media"), object(), PinRef("D24", "sdcard.cs"))
    assert isinstance(raised.value.__cause__, OSError)


# ---------------------------------------------------------------------------
# Optional driver libraries
# ---------------------------------------------------------------------------


_OPTIONAL_PARTS = {
    "matrix_pixels": ("adafruit_is31fl3741", "adafruit_is31fl3741.adafruit_rgbmatrixqt"),
    "neopixel_strip": ("neopixel",),
    "accelerometer": ("adafruit_lis3dh",),
    "magnetometer": ("adafruit_mmc56x3",),
    "haptic_output": ("adafruit_drv2605",),
    "audio_output": ("audiobusio", "audiocore", "audiomixer"),
    "ir_reader": ("pulseio",),
    "ir_writer": ("pulseio", "rp2pio"),
    "radio_transport": ("adafruit_rfm69",),
    "storage": ("sdcardio", "storage"),
}


_REQUESTS: dict[str, Callable[[CircuitPythonParts], object]] = {
    "matrix_pixels": lambda parts: parts.matrix_pixels(_matrix(), object()),
    "neopixel_strip": lambda parts: parts.neopixel_strip(
        _strip({"personal": range(0, 4)}), PinRef("D5", "pixels.pin")
    ),
    "accelerometer": lambda parts: parts.accelerometer(I2CDeviceConfig(), object()),
    "magnetometer": lambda parts: parts.magnetometer(I2CDeviceConfig(), object()),
    "haptic_output": lambda parts: parts.haptic_output(I2CDeviceConfig(), object()),
    "audio_output": lambda parts: parts.audio_output(_audio(), AudioRegistry(), *_I2S_PINS),
    "ir_reader": lambda parts: parts.ir_reader(PinRef("GP7", "ir.rx")),
    "ir_writer": lambda parts: parts.ir_writer("line", PinRef("GP8", "ir.line")),
    "radio_transport": lambda parts: parts.radio_transport(
        RadioConfig("D10", "D11", 433.0, 7), object(), *_RADIO_PINS
    ),
    "storage": lambda parts: parts.storage(
        SDCardConfig("D24"), object(), PinRef("D24", "sdcard.cs")
    ),
}


@pytest.fixture
def libraries_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every optional part's driver library unimportable, as on a board without them."""
    for library in sum(_OPTIONAL_PARTS.values(), ()):
        monkeypatch.setitem(sys.modules, library, None)
    for module in (
        "hardware.circuitpython.audio_output",
        "hardware.circuitpython.drv2605_output",
        "hardware.circuitpython.rfm69_radio_transport",
        "hardware.circuitpython.sdcard_storage",
    ):
        monkeypatch.delitem(sys.modules, module, raising=False)


@pytest.mark.parametrize("part", _OPTIONAL_PARTS)
def test_requesting_a_part_whose_driver_library_is_missing_raises_import_error(
    libraries_missing: None, part: str
) -> None:
    parts = CircuitPythonParts(
        _board("GP7", "GP8", "GP10", "GP11", "GP12", "D5", "D10", "D11", "D24")
    )

    with pytest.raises(ImportError):
        _REQUESTS[part](parts)


def test_button_reader_builds_and_reads_while_every_optional_library_is_missing(
    libraries_missing: None, gpio: list[_FakeDigitalInOut]
) -> None:
    read = CircuitPythonParts(_board("D9")).button_reader(PinRef("D9", "buttons[0]"))
    (pin,) = gpio

    pin.value = False

    assert read() is False

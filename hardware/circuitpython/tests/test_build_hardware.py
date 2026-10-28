"""``build_hardware`` boots a board through the Device assembly with ``CircuitPythonParts``.

What the assembly decides is tested in ``hardware/shared/tests/test_device_assembly.py``
and each part in ``test_circuitpython_parts.py``; these tests cover only what the
entry point adds: a driver-free import, the injected I2C bus, and ``open_config_i2c``,
which opens the config's I2C bus ahead of a boot so a profiler can wrap and inject it.
"""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import pytest

from engine.log import Logger
from hardware.circuitpython.device_builder import build_hardware, open_config_i2c
from hardware.shared.device_config import parse_device_config

_DRIVER_LIBRARIES = (
    "adafruit_is31fl3741",
    "adafruit_is31fl3741.adafruit_rgbmatrixqt",
    "neopixel",
    "pulseio",
    "audiobusio",
    "audiocore",
    "audiomixer",
    "adafruit_lis3dh",
    "adafruit_mmc56x3",
    "adafruit_drv2605",
    "adafruit_rfm69",
    "sdcardio",
    "storage",
    "rp2pio",
    "adafruit_pioasm",
)


def test_importing_the_entry_point_imports_no_driver_library(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A prop's boot imports this before knowing its config; each library
    # is imported only by the part that needs it.
    for name in list(sys.modules):
        if name.startswith("hardware.circuitpython") or name in _DRIVER_LIBRARIES:
            monkeypatch.delitem(sys.modules, name)

    import hardware.circuitpython.device_builder  # noqa: F401

    assert [name for name in _DRIVER_LIBRARIES if name in sys.modules] == []


class _FakeLis3dh:
    def __init__(self, i2c: object, **kwargs: object) -> None:
        self.i2c = i2c


@pytest.fixture
def board(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """A board whose default SPI bus builds, with a fake LIS3DH library installed."""
    lis3dh = ModuleType("adafruit_lis3dh")
    lis3dh.LIS3DH_I2C = _FakeLis3dh  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "adafruit_lis3dh", lis3dh)
    return SimpleNamespace(SPI=object)


def test_an_injected_i2c_bus_is_narrated_and_is_the_bus_i2c_parts_are_built_on(
    board: SimpleNamespace,
) -> None:
    injected = object()
    fragments: list[str] = []

    hw = build_hardware(
        parse_device_config({"accelerometer": {}}),
        board_module=board,
        i2c=injected,
        logger=Logger("[hw]", fragments.append),
    )

    assert "[hw] i2c default ok\n" in "".join(fragments)
    assert isinstance(hw.accelerometer, _FakeLis3dh)
    assert hw.accelerometer.i2c is injected


def test_disabled_i2c_ignores_an_injected_bus(board: SimpleNamespace) -> None:
    config = parse_device_config(
        {"i2c": {"enabled": False, "scl": "GP5", "sda": "GP4"}, "accelerometer": {}}
    )

    expected = "^accelerometer section is declared but no I2C bus is available$"
    with pytest.raises(RuntimeError, match=expected):
        build_hardware(config, board_module=board, i2c=object())


class _FakeI2C:
    """A ``busio.I2C`` on ``(scl, sda)``; raises as the real one does when nothing pulls it up."""

    pulled_up = True

    def __init__(self, scl: object, sda: object) -> None:
        if not _FakeI2C.pulled_up:
            raise RuntimeError("No pull up found on SDA or SCL; check your wiring")
        self.pins = (scl, sda)


@pytest.fixture
def busio(monkeypatch: pytest.MonkeyPatch) -> list[_FakeI2C]:
    """Fake ``busio.I2C``; returns every bus built."""
    _FakeI2C.pulled_up = True
    built: list[_FakeI2C] = []

    def _i2c(scl: object, sda: object) -> _FakeI2C:
        built.append(_FakeI2C(scl, sda))
        return built[-1]

    monkeypatch.setattr(sys.modules["busio"], "I2C", _i2c, raising=False)
    return built


def _pins(*names: str) -> SimpleNamespace:
    return SimpleNamespace(**{name: object() for name in names})


_DECLARED_I2C = {"i2c": {"sda": "GP4", "scl": "GP5"}}


def test_open_config_i2c_opens_a_bus_on_the_declared_pins(busio: list[_FakeI2C]) -> None:
    board = _pins("GP4", "GP5")

    bus = open_config_i2c(parse_device_config(_DECLARED_I2C), board)

    assert busio == [bus]
    assert bus.pins == (board.GP5, board.GP4)


def test_open_config_i2c_opens_a_bus_on_the_board_defaults_without_an_i2c_section(
    busio: list[_FakeI2C],
) -> None:
    board = _pins("SCL", "SDA")

    bus = open_config_i2c(parse_device_config({}), board)

    assert isinstance(bus, _FakeI2C)
    assert bus.pins == (board.SCL, board.SDA)


def test_open_config_i2c_with_an_unknown_pin_raises_value_error_naming_its_field(
    busio: list[_FakeI2C],
) -> None:
    config = parse_device_config({"i2c": {"sda": "NONEXISTENT_PIN", "scl": "GP5"}})

    with pytest.raises(ValueError, match=r"^i2c\.sda: pin 'NONEXISTENT_PIN' not found on board$"):
        open_config_i2c(config, _pins("GP5"))


def test_open_config_i2c_with_i2c_disabled_opens_no_bus(busio: list[_FakeI2C]) -> None:
    config = parse_device_config({"i2c": {**_DECLARED_I2C["i2c"], "enabled": False}})

    assert open_config_i2c(config, _pins("GP4", "GP5", "SCL", "SDA")) is None
    assert busio == []


def test_open_config_i2c_with_nothing_pulling_the_bus_up_opens_no_bus(
    busio: list[_FakeI2C],
) -> None:
    _FakeI2C.pulled_up = False

    assert open_config_i2c(parse_device_config({}), _pins("SCL", "SDA")) is None


def test_open_config_i2c_never_opens_the_never_reset_stemma_bus(busio: list[_FakeI2C]) -> None:
    # board.STEMMA_I2C() holds never_reset, leaving the peripheral claimed for
    # the next program; a plain busio.I2C is torn down on reload.
    stemma_calls: list[None] = []
    board = _pins("GP4", "GP5")
    board.STEMMA_I2C = lambda: stemma_calls.append(None)

    bus = open_config_i2c(parse_device_config(_DECLARED_I2C), board)

    assert stemma_calls == []
    assert busio == [bus]

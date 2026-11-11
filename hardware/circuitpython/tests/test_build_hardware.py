"""``build_hardware`` boots a board through the Device assembly with ``CircuitPythonParts``.

What the assembly decides is tested in ``hardware/shared/tests/test_device_assembly.py``
and each part in ``test_circuitpython_parts.py``; these tests cover only what the
entry point adds: a driver-free import, and a boot that opens its own board's
``default`` I2C bus.
"""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from typing import ClassVar

import pytest

from engine.log import Logger
from hardware.circuitpython.device_builder import build_hardware
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
    import hardware

    monkeypatch.setattr(hardware, "circuitpython", sys.modules["hardware.circuitpython"])
    for name in list(sys.modules):
        if name.startswith("hardware.circuitpython") or name in _DRIVER_LIBRARIES:
            monkeypatch.delitem(sys.modules, name)

    import hardware.circuitpython.device_builder

    assert [name for name in _DRIVER_LIBRARIES if name in sys.modules] == []


class _FakeLis3dh:
    """A LIS3DH remembering the bus it was built on; every one built lands in ``built``."""

    built: ClassVar[list[_FakeLis3dh]] = []

    def __init__(self, i2c: object, **kwargs: object) -> None:
        self.i2c = i2c
        _FakeLis3dh.built.append(self)


@pytest.fixture
def lis3dh_board(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """A board whose default SPI bus builds, with a fake LIS3DH library installed."""
    lis3dh = ModuleType("adafruit_lis3dh")
    monkeypatch.setattr(lis3dh, "LIS3DH_I2C", _FakeLis3dh, raising=False)
    monkeypatch.setattr(_FakeLis3dh, "built", [])
    monkeypatch.setitem(sys.modules, "adafruit_lis3dh", lis3dh)
    return SimpleNamespace(SPI=object)


def test_an_i2c_part_on_an_undeclared_default_without_a_board_i2c_bus_is_rejected(
    lis3dh_board: SimpleNamespace,
) -> None:
    with pytest.raises(
        RuntimeError, match=r"^accelerometer joins I2C bus 'default' but no I2C bus is available$"
    ):
        build_hardware(parse_device_config({"accelerometer": {}}), board_module=lis3dh_board)


class _FakeI2C:
    """A ``busio.I2C`` remembering the ``(scl, sda)`` pins it was opened on."""

    def __init__(self, scl: object, sda: object) -> None:
        self.pins = (scl, sda)


@pytest.fixture
def i2c_buses(monkeypatch: pytest.MonkeyPatch) -> list[_FakeI2C]:
    """Fake ``busio.I2C``; returns every bus built."""
    built: list[_FakeI2C] = []

    def _i2c(scl: object, sda: object) -> _FakeI2C:
        built.append(_FakeI2C(scl, sda))
        return built[-1]

    monkeypatch.setattr(sys.modules["busio"], "I2C", _i2c, raising=False)
    return built


def test_i2c_parts_are_built_on_the_default_bus_the_boot_opens_on_the_board_pins(
    lis3dh_board: SimpleNamespace, i2c_buses: list[_FakeI2C]
) -> None:
    lis3dh_board.SCL, lis3dh_board.SDA = object(), object()

    build_hardware(parse_device_config({"accelerometer": {}}), board_module=lis3dh_board)

    (chip,) = _FakeLis3dh.built
    assert i2c_buses == [chip.i2c]
    assert isinstance(chip.i2c, _FakeI2C)
    assert chip.i2c.pins == (lis3dh_board.SCL, lis3dh_board.SDA)


def test_the_default_i2c_bus_the_boot_opens_on_the_board_pins_is_narrated_as_the_board_bus(
    lis3dh_board: SimpleNamespace, i2c_buses: list[_FakeI2C]
) -> None:
    lis3dh_board.SCL, lis3dh_board.SDA = object(), object()
    fragments: list[str] = []

    build_hardware(
        parse_device_config({"accelerometer": {}}),
        board_module=lis3dh_board,
        logger=Logger("[hw]", fragments.append),
    )

    assert "[hw] i2c default board ok\n" in "".join(fragments)

"""The physical device's entry point: boots a board through the Device assembly.

Deploy-watch only: imports board and busio. What a config builds is decided by
:func:`~hardware.shared.device_assembly.assemble_device`; how each part is
built on a board lives in :class:`~hardware.circuitpython.circuitpython_parts.CircuitPythonParts`.
"""

from __future__ import annotations

import board
import busio

from engine.log import Logger
from hardware.circuitpython.circuitpython_parts import CircuitPythonParts, SdCardMountError
from hardware.shared.device_assembly import assemble_device
from hardware.shared.device_config import DeviceConfig
from hardware.shared.device_config import load_device_config as _load_shared_device_config
from hardware.shared.device_hardware import DeviceHardware
from hardware.shared.device_parts import PinRef

__all__ = [
    "SdCardMountError",
    "build_hardware",
    "load_device_config",
    "open_config_i2c",
]


def open_config_i2c(device_config: DeviceConfig, board_module: object = board) -> busio.I2C | None:
    """Return an I2C bus on *device_config*'s declared (or board-default) SDA/SCL pins.

    For callers that need the bus before :func:`build_hardware` -- e.g. a
    profiler that wraps it in ``CountingI2C`` and injects it back through
    ``build_hardware``'s ``i2c=``, so it lands on exactly the pins the board
    would have chosen. ``i2c`` disabled builds no bus; no pull-up returns
    ``None``; an unknown pin raises a field-named ``ValueError``.

    Unlike ``board.STEMMA_I2C()``, the bus is a plain ``busio.I2C`` that
    CircuitPython tears down on reload, so a profiler run never leaves the
    I2C peripheral claimed for the next program.
    """
    i2c_config = device_config.i2c
    parts = CircuitPythonParts(board_module)
    if i2c_config is None:
        return parts.i2c_bus(None, None)
    if not i2c_config.enabled:
        return None
    return parts.i2c_bus(PinRef(i2c_config.scl, "i2c.scl"), PinRef(i2c_config.sda, "i2c.sda"))


def load_device_config() -> DeviceConfig:
    """Load and parse aura-device.json from the device root."""
    return _load_shared_device_config()


def build_hardware(
    config: DeviceConfig,
    board_module: object = board,
    i2c: busio.I2C | None = None,
    logger: Logger | None = None,
) -> DeviceHardware:
    """Boot *board_module* through the Device assembly, narrating to *logger* (omitted: silent).

    *i2c*, if supplied, is the bus every I2C part is built on, unless the
    config disables ``i2c``. Single-call: pins are claimed without deiniting.
    """
    return assemble_device(config, CircuitPythonParts(board_module, i2c), logger)

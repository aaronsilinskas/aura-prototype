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
from hardware.shared.device_assembly import assemble_device, open_i2c
from hardware.shared.device_config import DeviceConfig
from hardware.shared.device_config import load_device_config as _load_shared_device_config
from hardware.shared.device_hardware import DeviceHardware

__all__ = [
    "SdCardMountError",
    "build_hardware",
    "load_device_config",
    "open_config_i2c",
]


def open_config_i2c(device_config: DeviceConfig, board_module: object = board) -> busio.I2C | None:
    """Return the I2C bus a boot of *device_config* would build, ahead of :func:`build_hardware`.

    For a profiler that wraps the bus (e.g. in ``CountingI2C``) and injects it
    back through ``build_hardware``'s ``i2c=``. A plain ``busio.I2C``, never the
    ``never_reset`` ``board.STEMMA_I2C()``, so it is released on reload.
    """
    return open_i2c(device_config.i2c, CircuitPythonParts(board_module))


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

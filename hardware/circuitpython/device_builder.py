"""The physical device's entry point: boots a board through the Device assembly.

Deploy-watch only: imports board. What a config builds is decided by
:func:`~hardware.shared.device_assembly.assemble_device`; how each part is
built on a board lives in :class:`~hardware.circuitpython.circuitpython_parts.CircuitPythonParts`.
"""

from __future__ import annotations

import board

from engine.log import Logger
from hardware.circuitpython.circuitpython_parts import CircuitPythonParts, SdCardMountError
from hardware.shared.device_assembly import assemble_device
from hardware.shared.device_config import DeviceConfig
from hardware.shared.device_config import load_device_config as _load_shared_device_config
from hardware.shared.device_hardware import DeviceHardware

__all__ = [
    "SdCardMountError",
    "build_hardware",
    "load_device_config",
]


def load_device_config() -> DeviceConfig:
    """Load and parse aura-device.json from the device root."""
    return _load_shared_device_config()


def build_hardware(
    config: DeviceConfig,
    board_module: object = board,
    logger: Logger | None = None,
) -> DeviceHardware:
    """Boot *board_module* through the Device assembly, narrating to *logger* (omitted: silent).

    Single-call: pins are claimed without deiniting.
    """
    return assemble_device(config, CircuitPythonParts(board_module), logger)

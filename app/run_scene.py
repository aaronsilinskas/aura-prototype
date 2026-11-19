"""Device-only scene entry point — brings hardware up and runs any standard-IR scene.

``build_hardware`` imports board, busio, pulseio and digitalio, so this module
runs only on the device; the board-free boot lives in ``app.scene_composition``.
"""

from __future__ import annotations

import gc

import microcontroller

from app.scene_composition import build_scene_boot
from engine.log import Logger
from hardware.circuitpython.device_builder import build_hardware, load_device_config
from hardware.shared.device_boot import read_boot_mapping

__all__ = ["run_scene"]


def run_scene() -> None:
    """Bring hardware up via ``build_hardware`` and run the resolved boot scene forever.

    Hardware comes up before the boot because the mounted SD card can name the
    scene, so ``hw.storage`` must exist before a scene name is known to be valid.
    """
    hw_logger = Logger("[hw]")
    hw = build_hardware(load_device_config(), logger=hw_logger)

    tick = build_scene_boot(
        hw, read_boot_mapping(), reset=microcontroller.reset, logger=hw_logger
    ).tick

    while True:
        tick()
        gc.collect()

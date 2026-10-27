"""Device-only scene runtime — brings hardware up and runs any standard-IR scene.

Deploy-watch only: ``build_hardware`` imports board, busio, pulseio, digitalio.
Imported on-device under CircuitPython, never exercised by CPython pytest. The
board-free wiring lives in ``app.scene_composition`` so it can be
unit-tested under CPython without the board imports this module pulls in.
"""

from __future__ import annotations

import gc

import microcontroller

from app.scene_composition import build_scene_boot
from engine.log import Logger
from hardware.circuitpython.device_builder import build_hardware, load_device_config
from hardware.shared.device_settings import read_settings_mapping

__all__ = ["run_scene"]


def run_scene() -> None:
    """Bring hardware up via ``build_hardware`` and run the resolved boot scene forever.

    Builds the hardware first, so that ``hw.storage`` reflects whatever SD
    card is mounted, then boots through
    :func:`app.scene_composition.build_scene_boot`, the board-free boot the
    Simulated device shares, with the flash ``aura-settings.json`` as the
    settings and ``microcontroller.reset`` as the reset. That the card can
    name the scene is why hardware always comes up before a scene name is
    known to be valid.

    Each tick runs the per-tick body that boot returns, the same
    :func:`app.scene_composition.build_scene_tick` the Simulated device
    drives, then ``gc.collect()``. A live ``[hw]``-tagged
    :class:`~engine.log.Logger` narrates hardware setup and the boot on
    stdout.

    This is the only scene path that names ``microcontroller.reset``. Not
    unit-testable, since ``build_hardware`` needs CircuitPython board
    imports; validate via deploy-watch. The boot itself is unit-tested in
    ``app/tests/test_scene_composition.py`` and exercised by every Simulated
    device.
    """
    hw_logger = Logger("[hw]")
    hw = build_hardware(load_device_config(), logger=hw_logger)

    _scene_name, tick = build_scene_boot(
        hw, read_settings_mapping(), reset=microcontroller.reset, logger=hw_logger
    )

    while True:
        tick()
        gc.collect()

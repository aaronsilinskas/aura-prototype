"""Device-only scene runtime — brings hardware up and runs any standard-IR scene.

Deploy-watch only: ``build_hardware`` imports board, busio, pulseio, digitalio.
Imported on-device under CircuitPython, never exercised by CPython pytest. The
board-free wiring lives in ``app.scene_composition`` so it can be
unit-tested under CPython without the board imports this module pulls in.
"""

from __future__ import annotations

import gc

import microcontroller

from app.scene_composition import (
    build_scene_runtime,
    build_scene_tick,
    resolve_boot_scene_name,
    resolve_ir_codec,
    scan_boot_scene_registry,
)
from engine.log import Logger
from hardware.circuitpython.device_builder import build_hardware, load_device_config
from hardware.shared.device_reboot import DeviceSceneReboot
from hardware.shared.device_settings import read_settings_mapping

__all__ = ["run_scene"]


def run_scene() -> None:
    """Bring hardware up via ``build_hardware`` and run the resolved boot scene forever.

    Calls ``build_hardware`` first, with no codec override (it wires the IR
    subsystem with its default Aura wire-frame). Only after the build returns
    -- once ``hw.storage`` reflects whatever SD card is mounted -- is the
    complete boot-time scene registry built, via
    ``scan_boot_scene_registry(hw.storage)``: flash ``packs/scenes`` plus,
    when a card is mounted, its ``aura_packs/scenes``, in the one registry
    every remaining boot step shares. The boot scene is then resolved via
    ``resolve_boot_scene_name``: a persisted SD ``scene`` (``aura-state.json``)
    overrides the flash ``default_scene`` (``aura-settings.json``), falling
    back to the flash default on a card-less device (``hw.storage is None``)
    or when no override is persisted, and raising when neither is set. The
    resolved name is validated against the complete registry as part of that
    same call, so an unknown name -- persisted or flash-authored, flash or
    card scene -- fails loudly, naming the known scenes. This is also what
    lets a card scene named as the persisted ``scene`` or the flash
    ``default_scene`` resolve instead of raising "unknown scene."

    Accepted consequence: unlike the old flash-only resolution this replaces,
    that unknown-scene fail-fast can no longer run ahead of ``build_hardware``
    -- the SD override that can feed the name only exists once storage is
    mounted, so hardware is always brought up before a scene name is known to
    be valid.

    Once the scene name is resolved, this resolves the scene's declared IR
    wire-frame codec via ``resolve_ir_codec`` (Aura by default, Tag when the
    scene declares it) and applies it onto the built ``hw.ir`` via
    ``InfraredTransceiver.apply_codec``, before the first tick -- so the
    correct codec is still in effect from the first tick even though it is
    selected after the build. The same complete registry is passed into
    ``build_scene_runtime``, which now requires it and scans no scenes of its
    own, so a scene is scanned exactly once for the whole boot sequence.

    Each tick runs the shared per-tick body from
    :func:`app.scene_composition.build_scene_tick` (the same one the Simulated
    device drives), then ``gc.collect()``. Constructs a live ``[hw]``-tagged
    :class:`~engine.log.Logger` and passes it to ``build_hardware`` so the
    on-device path always gets hardware setup narration on stdout, with no
    opt-in required.

    This is the only place the live ``DeviceSceneReboot``
    (:mod:`hardware.shared.device_reboot`) is constructed and threaded into
    ``build_scene_runtime`` as the ``SceneReboot`` port, and the only scene
    path that names ``microcontroller.reset``, which it injects as the reset; see
    that module for why it takes the booted *scene_name* and ``hw.storage``.

    Not unit-testable — ``build_hardware`` requires
    CircuitPython board imports; validate via deploy-watch. The board-free
    boot-scene resolution this reorder relies on (``resolve_boot_scene_name``,
    composing ``hardware.shared.scene_selection.resolve_boot_scene`` with
    ``resolve_known_scene``) is unit-tested separately in
    ``app/tests/test_scene_composition.py``.
    """
    config = load_device_config()
    hw_logger = Logger("[hw]")
    hw = build_hardware(config, logger=hw_logger)

    scene_registry = scan_boot_scene_registry(hw.storage)

    settings_mapping = read_settings_mapping()
    scene_name = resolve_boot_scene_name(
        scene_registry, hw.storage, settings_mapping, logger=hw_logger
    )

    ir_encoder, ir_decoder = resolve_ir_codec(scene_registry, scene_name)
    if hw.ir is not None:
        hw.ir.apply_codec(ir_encoder, ir_decoder)

    scene_reboot = DeviceSceneReboot(
        hw.storage, booted_scene=scene_name, reset=microcontroller.reset, logger=hw_logger
    )
    runtime = build_scene_runtime(
        hw, scene_name, scene_registry=scene_registry, scene_reboot=scene_reboot
    )
    tick = build_scene_tick(hw, runtime)

    while True:
        tick()
        gc.collect()

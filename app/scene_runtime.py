"""Device-only scene runtime — brings hardware up and runs any standard-IR scene.

Deploy-watch only: ``build_hardware`` imports board, busio, pulseio, digitalio.
Imported on-device under CircuitPython, never exercised by CPython pytest. The
board-free wiring lives in ``app.scene_composition`` so it can be
unit-tested under CPython without the board imports this module pulls in.
"""

from __future__ import annotations

import gc

from app.scene_composition import build_scene_runtime, resolve_boot_scene_name, resolve_ir_codec
from engine.input import AccelerationData, ButtonData, InputEvents, MagneticData
from engine.log import Logger
from engine.network import NetworkEvents
from engine.scene import SceneRegistry
from hardware.circuitpython.device_builder import build_hardware, load_device_config
from hardware.circuitpython.device_reboot import DeviceSceneReboot
from hardware.shared.device_settings import read_settings_mapping

try:
    from typing import Final
except ImportError:
    pass  # typing not available on all embedded runtimes

_TELEMETRY_PRINT_INTERVAL: Final = 1.0  # seconds

__all__ = ["run_scene"]


def run_scene() -> None:
    """Bring hardware up via ``build_hardware`` and run the resolved boot scene forever.

    Scans a single ``SceneRegistry`` up front, then calls ``build_hardware``
    with no codec override (it wires the IR subsystem with its default Aura
    wire-frame). Only after the build returns -- once ``hw.storage`` reflects
    whatever SD card is mounted -- is the boot scene resolved, via
    ``resolve_boot_scene_name``: a persisted SD ``scene`` (``aura-state.json``)
    overrides the flash ``default_scene`` (``aura-settings.json``), falling
    back to the flash default on a card-less device (``hw.storage is None``)
    or when no override is persisted, and raising when neither is set. The
    resolved name is validated against the scanned registry as part of that
    same call, so an unknown name -- persisted or flash-authored -- fails
    loudly, naming the known scenes.

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
    selected after the build. The same registry is passed into
    ``build_scene_runtime`` so the scene is scanned exactly once for the
    whole boot sequence.

    Drives ``runtime.ir.update()`` every tick (see
    :class:`~hardware.shared.ir_transceiver.InfraredTransceiver`), which owns
    the pump-before-receive order and always runs regardless of whether a
    scene is active — a no-op when ``runtime.ir`` is ``None`` (no ``ir``
    section wired). Prints the telemetry line from
    ``runtime.ir.telemetry_line()`` (see :mod:`hardware.shared.ir_telemetry`)
    when it returns one — the receiver itself gates on whether a counter
    changed since the last call. Also drives ``runtime.radio.update()`` every
    tick (see
    :class:`~hardware.shared.radio_transceiver.RadioTransceiver`), the radio
    parallel to the IR receive block — likewise a no-op when ``runtime.radio``
    is ``None`` (no radio peripheral wired). Builds the queued
    ``NetworkEvents.RadioReceived`` event locally, next to the ``IRReceived``
    block, from ``radio.received``/``radio.last_sender`` — ``RadioTransceiver``
    itself builds no game event. Constructs a live ``[hw]``-tagged
    :class:`~engine.log.Logger` and passes it to ``build_hardware`` so the
    on-device path always gets hardware setup narration on stdout, with no
    opt-in required.

    Constructs the live ``DeviceSceneReboot``
    (:mod:`hardware.circuitpython.device_reboot`) with the resolved
    *scene_name* as its booted-scene and ``hw.storage``, then threads it into
    ``build_scene_runtime`` as the board-free ``SceneReboot`` port — the only
    place that adapter is built, so no rule needs to know its own scene name
    to reboot back to it later via ``state.scene_controls.reboot_to_previous``.

    Not unit-testable — ``build_hardware`` requires
    CircuitPython board imports; validate via deploy-watch. The board-free
    boot-scene resolution this reorder relies on (``resolve_boot_scene_name``,
    composing ``hardware.shared.scene_selection.resolve_boot_scene`` with
    ``resolve_known_scene``) is unit-tested separately in
    ``app/tests/test_scene_composition.py``.
    """
    scene_registry = SceneRegistry()
    scene_registry.scan_dir("packs/scenes", "packs.scenes")

    config = load_device_config()
    hw_logger = Logger("[hw]")
    hw = build_hardware(config, logger=hw_logger)

    settings_mapping = read_settings_mapping()
    scene_name = resolve_boot_scene_name(
        scene_registry, hw.storage, settings_mapping, logger=hw_logger
    )

    ir_encoder, ir_decoder = resolve_ir_codec(scene_registry, scene_name)
    if hw.ir is not None:
        hw.ir.apply_codec(ir_encoder, ir_decoder)

    scene_reboot = DeviceSceneReboot(hw.storage, booted_scene=scene_name, logger=hw_logger)
    runtime = build_scene_runtime(
        hw, scene_name, scene_registry=scene_registry, scene_reboot=scene_reboot
    )
    manager = runtime.manager
    effect_manager = runtime.effect_manager
    timer = runtime.timer
    ir = runtime.ir
    radio = runtime.radio

    _button_data = ButtonData({})
    _acceleration = AccelerationData(0.0, 0.0, 0.0) if hw.accelerometer is not None else None
    _magnetic = MagneticData(0.0, 0.0, 0.0) if hw.magnetometer is not None else None
    _input_event = InputEvents.Sensors(_button_data, _acceleration, _magnetic)

    _last_telemetry_print_total = 0.0

    while True:
        hw.buttons.update(timer.elapsed, _button_data)

        if _acceleration is not None:
            try:
                ax, ay, az = hw.accelerometer.acceleration
                _acceleration.x = ax
                _acceleration.y = ay
                _acceleration.z = az
            except Exception:
                pass  # keep last good values; None signals missing hardware, not read failure

        if _magnetic is not None:
            try:
                mx, my, mz = hw.magnetometer.magnetic
                _magnetic.x = mx
                _magnetic.y = my
                _magnetic.z = mz
            except Exception:
                pass  # keep last good values; None signals missing hardware, not read failure

        # Unconditional, before the active_state check: a send can be in
        # flight across a scene transition, and ir.update() always pumps so
        # a deferred end_transmit still arms the flush latch its own receive
        # consumes this same tick. It also always receives when a receiver
        # is wired, so a packet decoded while no scene is active is
        # drained-and-dropped here rather than left to overflow — only the
        # queuing below is conditional on a scene being active. A no-op
        # when no ir section is wired at all (ir is None).
        if ir is not None:
            ir.update()

        # Same unconditional rationale as ir.update() above: radio.update()
        # always polls for a waiting packet regardless of whether a scene is
        # active, so a packet decoded with no active scene is simply never
        # queued below rather than left to build up in the transport. A
        # no-op when no radio peripheral is wired at all (radio is None).
        if radio is not None:
            radio.update()

        active_state = manager.active_state

        if active_state is not None:
            if ir is not None and ir.received is not None:
                active_state.queue_event(
                    NetworkEvents.IRReceived(
                        ir.received,
                        ir.last_signal_strength,
                        ir.last_error_margin,
                        best_receiver=None,
                    )
                )
            if radio is not None and radio.received is not None:
                active_state.queue_event(
                    NetworkEvents.RadioReceived(radio.received, str(radio.last_sender))
                )
            active_state.queue_event(_input_event)

        manager.update()
        effect_manager.update(timer)

        if timer.total - _last_telemetry_print_total >= _TELEMETRY_PRINT_INTERVAL:
            _last_telemetry_print_total = timer.total
            line = ir.telemetry_line() if ir is not None else None
            if line is not None:
                print(line)

        gc.collect()

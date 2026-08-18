"""Device-only scene runtime — brings hardware up and runs any standard-IR scene.

Deploy-watch only: ``build_hardware`` imports board, busio, pulseio, digitalio.
Imported on-device under CircuitPython, never exercised by CPython pytest. The
board-free wiring lives in ``app.scene_composition`` so it can be
unit-tested under CPython without the board imports this module pulls in.
"""

from __future__ import annotations

import gc

from app.scene_composition import _resolve_known_scene, build_scene_runtime, resolve_ir_codec
from engine.input import AccelerationData, ButtonData, InputEvents, MagneticData
from engine.log import Logger
from engine.network import NetworkEvents
from engine.scene import SceneRegistry
from hardware.circuitpython.device_builder import build_hardware, load_device_config

try:
    from typing import Final
except ImportError:
    pass  # typing not available on all embedded runtimes

_TELEMETRY_PRINT_INTERVAL: Final = 1.0  # seconds

__all__ = ["run_scene"]


def run_scene(scene_name: str) -> None:
    """Bring hardware up via ``build_hardware`` and run *scene_name* forever.

    Scans a single ``SceneRegistry`` up front and validates *scene_name*
    against it via ``_resolve_known_scene`` before any hardware is built, so
    an unknown scene name fails once, naming the known scenes, without ever
    touching the board. The same scan then resolves the scene's declared IR
    wire-frame codec via ``resolve_ir_codec`` (Aura by default, Tag when the
    scene declares it) and forwards the instantiated encoder/decoder into
    ``build_hardware``, so the correct codec is wired from the first tick.
    The same registry is passed into ``build_scene_runtime`` so the scene is
    scanned exactly once for the whole boot sequence.

    Drives ``runtime.ir.update()`` every tick (see
    :class:`~hardware.shared.ir_manager.InfraredManager`), which owns the
    pump-before-receive order and always runs regardless of whether a scene
    is active. Prints the telemetry line from ``runtime.ir.telemetry_line()``
    (see :mod:`hardware.shared.ir_telemetry`) when it returns one — the
    receiver itself gates on whether a counter changed since the last call.
    Also drives ``runtime.radio.update()`` every tick (see
    :class:`~hardware.shared.radio_manager.RadioManager`), the radio parallel
    to the IR receive block. Constructs a live ``[hw]``-tagged
    :class:`~engine.log.Logger` and passes it to ``build_hardware`` so the
    on-device path always gets hardware setup narration on stdout, with no
    opt-in required. Not unit-testable — ``build_hardware`` requires
    CircuitPython board imports; validate via deploy-watch.

    Args:
        scene_name: Name of the scene to load.
    """
    scene_registry = SceneRegistry()
    scene_registry.scan_dir("packs/scenes", "packs.scenes")
    _resolve_known_scene(scene_registry, scene_name)

    ir_encoder, ir_decoder = resolve_ir_codec(scene_registry, scene_name)

    config = load_device_config()
    hw_logger = Logger("[hw]")
    hw = build_hardware(config, ir_encoder=ir_encoder, ir_decoder=ir_decoder, logger=hw_logger)

    runtime = build_scene_runtime(hw, scene_name, scene_registry=scene_registry)
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
        # queuing below is conditional on a scene being active.
        ir.update()

        # Same unconditional rationale as ir.update() above: radio.update()
        # always polls for a waiting packet regardless of whether a scene is
        # active, so a packet decoded with no active scene is simply never
        # queued below rather than left to build up in the transport.
        radio.update()

        active_state = manager.active_state

        if active_state is not None:
            if ir.received is not None:
                active_state.queue_event(
                    NetworkEvents.IRReceived(
                        ir.received,
                        ir.last_signal_strength,
                        ir.last_error_margin,
                        best_receiver=None,
                    )
                )
            if radio.received is not None:
                active_state.queue_event(radio.received)
            active_state.queue_event(_input_event)

        manager.update()
        effect_manager.update(timer)

        if timer.total - _last_telemetry_print_total >= _TELEMETRY_PRINT_INTERVAL:
            _last_telemetry_print_total = timer.total
            line = ir.telemetry_line()
            if line is not None:
                print(line)

        gc.collect()

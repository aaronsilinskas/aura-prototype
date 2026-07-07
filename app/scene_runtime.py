"""Device-only scene runtime — brings hardware up and runs any standard-IR scene.

Deploy-watch only: ``build_hardware`` imports board, busio, pulseio, digitalio.
Imported on-device under CircuitPython, never exercised by CPython pytest. The
board-free wiring lives in ``app.scene_composition`` so it can be
unit-tested under CPython without the board imports this module pulls in.
"""

from __future__ import annotations

import gc

from app.scene_composition import build_scene_runtime
from engine.input import AccelerationData, ButtonData, InputEvents
from engine.network import NetworkEvents
from hardware.circuitpython.device_builder import build_hardware, load_device_config
from hardware.shared.ir_protocol import InfraredDecoder, InfraredEncoder

try:
    from typing import Final
except ImportError:
    pass  # typing not available on all embedded runtimes

_TELEMETRY_PRINT_INTERVAL: Final = 1.0  # seconds

__all__ = ["run_scene"]


def run_scene(
    scene_name: str,
    ir_encoder: InfraredEncoder | None = None,
    ir_decoder: InfraredDecoder | None = None,
) -> None:
    """Bring hardware up via ``build_hardware`` and run *scene_name* forever.

    Prints the telemetry line from ``hw.ir_receiver.telemetry_line()`` (see
    :mod:`hardware.shared.ir_telemetry`) when it returns one — the receiver
    itself gates on whether a counter changed since the last call. Not
    unit-testable — ``build_hardware`` requires CircuitPython board imports;
    validate via deploy-watch.

    Args:
        scene_name: Name of the scene to load.
        ir_encoder: Optional wire-frame-codec encoder forwarded to
            ``build_hardware``; defaults to the Aura wire-frame when omitted.
        ir_decoder: Optional wire-frame-codec decoder forwarded to
            ``build_hardware``; defaults to the Aura wire-frame when omitted.
    """
    config = load_device_config()
    hw = build_hardware(config, ir_encoder=ir_encoder, ir_decoder=ir_decoder)

    runtime = build_scene_runtime(hw, scene_name)
    manager = runtime.manager
    effect_manager = runtime.effect_manager
    timer = runtime.timer

    _button_data = ButtonData({})
    _acceleration = AccelerationData(0.0, 0.0, 0.0) if hw.accelerometer is not None else None
    _input_event = InputEvents.ButtonAndAcceleration(_button_data, _acceleration)

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

        active_state = manager.active_state

        # Outside the active_state guard and before receive(): a send can be
        # in flight across a scene transition, and end_transmit (fired here
        # when a deferred write completes) arms the flush latch this same
        # tick's receive() must consume. Pumped through transmit_pump, not
        # network_controls — poll_transmits is a runtime lifecycle concern,
        # not a rule-facing send, so it is reached through the type that
        # declares it rather than downcast through the send-only handle.
        hw.transmit_pump.poll_transmits()

        if active_state is not None and hw.ir_receiver is not None:
            ir_data = hw.ir_receiver.receive()
            if ir_data is not None:
                active_state.queue_event(
                    NetworkEvents.IRReceived(
                        ir_data,
                        hw.ir_receiver.last_signal_strength,
                        hw.ir_receiver.last_error_margin,
                        best_receiver=None,
                    )
                )

        if active_state is not None:
            active_state.queue_event(_input_event)

        manager.update()
        effect_manager.update(timer)

        if (
            hw.ir_receiver is not None
            and timer.total - _last_telemetry_print_total >= _TELEMETRY_PRINT_INTERVAL
        ):
            _last_telemetry_print_total = timer.total
            line = hw.ir_receiver.telemetry_line()
            if line is not None:
                print(line)

        gc.collect()

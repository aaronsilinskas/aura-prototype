"""Device-only scene runtime — brings hardware up and runs any standard-IR scene.

Deploy-watch only: ``build_hardware`` imports board, busio, pulseio, digitalio.
Imported on-device under CircuitPython, never exercised by CPython pytest.  The
pure scene-name resolver lives in ``hardware.shared.scene_selection`` so it can
be unit-tested under CPython without the board imports this module pulls in.
"""

from __future__ import annotations

import gc

from engine.effects.manager import EffectManager
from engine.engine import GameEngine
from engine.input import AccelerationData, ButtonData, InputEvents
from engine.network import NetworkEvents
from engine.packs import PackRegistry
from engine.scene import SceneManager, SceneRegistry
from engine.timer import Timer
from hardware.circuitpython.device_builder import build_hardware, load_device_config
from hardware.shared.ir_protocol import InfraredDecoder, InfraredEncoder
from hardware.shared.scene_selection import DEFAULT_SCENE

__all__ = ["run_scene"]


def _resolve_known_scene(scene_registry: SceneRegistry, scene_name: str) -> str:
    """Return *scene_name* if registered, else warn and fall back to ``DEFAULT_SCENE``."""
    names = scene_registry.names()
    if scene_name in names:
        return scene_name
    print(
        "unknown scene '"
        + scene_name
        + "'; known scenes: "
        + ", ".join(names)
        + " — falling back to '"
        + DEFAULT_SCENE
        + "'"
    )
    return DEFAULT_SCENE


def run_scene(
    scene_name: str,
    ir_encoder: InfraredEncoder | None = None,
    ir_decoder: InfraredDecoder | None = None,
) -> None:
    """Bring hardware up via ``build_hardware`` and run *scene_name* forever.

    Builds the effect/rule ``PackRegistry``s, ``GameEngine``, ``SceneRegistry``,
    and ``SceneManager``, loads the requested scene (falling back to
    ``DEFAULT_SCENE`` with a console message when the name is not registered),
    then drives the read-inputs → poll-IR → queue-events → ``manager.update()``
    → ``effect_manager.update(timer)`` loop on a single ``Timer``.  IR polling
    is skipped when no ``ir_receiver`` is present.

    Args:
        scene_name: Name of the scene to load.
        ir_encoder: Optional wire-frame-codec encoder forwarded to
            ``build_hardware``; defaults to the Aura wire-frame when omitted.
        ir_decoder: Optional wire-frame-codec decoder forwarded to
            ``build_hardware``; defaults to the Aura wire-frame when omitted.
    """
    config = load_device_config()
    hw = build_hardware(config, ir_encoder=ir_encoder, ir_decoder=ir_decoder)

    effect_registry = PackRegistry(item_attr="BUILD")
    effect_registry.scan_dir("packs/effects", "packs.effects")

    rule_registry = PackRegistry(item_attr="RULE")
    rule_registry.scan_dir("packs/rules", "packs.rules")

    effect_manager = EffectManager(registry=effect_registry, outputs=hw.outputs)

    timer = Timer()
    engine = GameEngine(
        effect_controls=effect_manager,
        network_controls=hw.network_controls,
        timer=timer,
    )

    scene_registry = SceneRegistry()
    scene_registry.scan_dir("packs/scenes", "packs.scenes")

    manager = SceneManager(engine, effect_registry, rule_registry, scene_registry)
    manager.load(_resolve_known_scene(scene_registry, scene_name))
    manager.update()  # applies the load transition; the scene is now active

    _button_data = ButtonData({})
    _acceleration = AccelerationData(0.0, 0.0, 0.0) if hw.accelerometer is not None else None
    _input_event = InputEvents.ButtonAndAcceleration(_button_data, _acceleration)

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
        gc.collect()

"""Device-only scene runtime — brings hardware up and runs any standard-IR scene.

Deploy-watch only: ``build_hardware`` imports board, busio, pulseio, digitalio.
Imported on-device under CircuitPython, never exercised by CPython pytest.  The
pure scene-name resolver lives in ``hardware.shared.scene_selection`` so it can
be unit-tested under CPython without the board imports this module pulls in.

----------------------------------------------------------------------------
SCRATCH-BRANCH INSTRUMENTATION — issue #505: scene-loop FPS investigation
----------------------------------------------------------------------------
This file is TEMPORARILY instrumented to attribute the 30-40% FPS regression
between the old propmaker_demo loop (~12-14 FPS) and the new scene_runtime loop
(8.4-9.78 FPS).  All instrumentation is reverted once measurements are recorded
on the issue.  Nothing here ships.

Module-level toggles (all default to False = production behaviour):
  SKIP_GC_COLLECT   — omit gc.collect() from the frame tail
  SKIP_ACCEL_READ   — skip the accelerometer I2C read + AccelerationData alloc
  SKIP_IR_RECEIVE   — skip ir_receiver.receive() + IRReceived event queue
  SKIP_DEBUG_PACK   — load-time toggle: omit debug rule pack from the registry

Pass selection (set exactly one to True):
  ENABLE_PASS1      — whole-frame FPS + allocation delta (trustworthy numbers)
  ENABLE_PASS2      — per-stage time.monotonic() brackets (distorted; orientation
                      only — timer float allocs contaminate allocation/gc figures)

Do NOT enable both passes in the same run.
----------------------------------------------------------------------------
"""

from __future__ import annotations

import gc
import time

from effects.performance import PerformanceTracker
from engine.effects.manager import EffectManager
from engine.engine import GameEngine
from engine.input import AccelerationData, InputEvents
from engine.network import NetworkEvents
from engine.packs import PackRegistry
from engine.scene import SceneManager, SceneRegistry
from engine.timer import Timer
from hardware.circuitpython.device_builder import build_hardware, load_device_config
from hardware.shared.ir_protocol import InfraredDecoder, InfraredEncoder
from hardware.shared.profiling_helpers import print_profile_header, print_stats_line
from hardware.shared.scene_selection import DEFAULT_SCENE

__all__ = ["run_scene"]

# ---------------------------------------------------------------------------
# Suspect toggles — set exactly one True per A/B run; default = production
# ---------------------------------------------------------------------------
SKIP_GC_COLLECT: bool = False
SKIP_ACCEL_READ: bool = False
SKIP_IR_RECEIVE: bool = False
SKIP_DEBUG_PACK: bool = False  # load-time: omits debug pack from rule registry

# ---------------------------------------------------------------------------
# Pass selection — set exactly ONE to True; never both in the same run
# ---------------------------------------------------------------------------
ENABLE_PASS1: bool = False  # whole-frame FPS + allocation delta (no inner timers)
ENABLE_PASS2: bool = False  # per-stage timers — allocation/gc figures are DISTORTED

_LOG_INTERVAL: float = 5.0


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
    if not SKIP_DEBUG_PACK:
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

    if ENABLE_PASS1:
        _run_pass1(hw, manager, effect_manager, timer)
    elif ENABLE_PASS2:
        _run_pass2(hw, manager, effect_manager, timer)
    else:
        _run_production(hw, manager, effect_manager, timer)


def _run_production(hw, manager, effect_manager, timer) -> None:  # type: ignore[no-untyped-def]
    """Production loop — no instrumentation.  All toggles still apply."""
    while True:
        button_data = hw.buttons.update(timer.elapsed)

        acceleration = None
        if not SKIP_ACCEL_READ and hw.accelerometer is not None:
            try:
                ax, ay, az = hw.accelerometer.acceleration
                acceleration = AccelerationData(ax, ay, az)
            except Exception:
                acceleration = None

        active_state = manager.active_state

        if not SKIP_IR_RECEIVE and active_state is not None and hw.ir_receiver is not None:
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
            active_state.queue_event(InputEvents.ButtonAndAcceleration(button_data, acceleration))

        manager.update()
        effect_manager.update(timer)

        if not SKIP_GC_COLLECT:
            gc.collect()


# ---------------------------------------------------------------------------
# Pass 1 — whole-frame FPS + whole-frame allocation delta
#
# Trustworthy numbers: PerformanceTracker snapshots gc.mem_alloc() at
# start_frame and complete_frame; no inner timers, so the measurement barely
# perturbs allocation.  Read FPS and Mem Delta Avg from the __STATS line.
# ---------------------------------------------------------------------------


def _run_pass1(hw, manager, effect_manager, timer) -> None:  # type: ignore[no-untyped-def]
    """Pass 1: whole-frame FPS + allocation delta (no per-stage timers)."""
    perf = PerformanceTracker(log_interval=_LOG_INTERVAL)
    print_profile_header(
        component="scene_runtime.pass1",
        sweep_axes=[
            "skip_gc",
            "skip_accel",
            "skip_ir",
            "skip_debug",
        ],
        sweep_values=[
            SKIP_GC_COLLECT,
            SKIP_ACCEL_READ,
            SKIP_IR_RECEIVE,
            SKIP_DEBUG_PACK,
        ],
        target_fps=0.0,
    )

    while True:
        perf.start_frame()

        button_data = hw.buttons.update(timer.elapsed)

        acceleration = None
        if not SKIP_ACCEL_READ and hw.accelerometer is not None:
            try:
                ax, ay, az = hw.accelerometer.acceleration
                acceleration = AccelerationData(ax, ay, az)
            except Exception:
                acceleration = None

        active_state = manager.active_state

        if not SKIP_IR_RECEIVE and active_state is not None and hw.ir_receiver is not None:
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
            active_state.queue_event(InputEvents.ButtonAndAcceleration(button_data, acceleration))

        manager.update()
        effect_manager.update(timer)

        if not SKIP_GC_COLLECT:
            gc.collect()

        if perf.complete_frame():
            print_stats_line(
                perf,
                skip_gc=SKIP_GC_COLLECT,
                skip_accel=SKIP_ACCEL_READ,
                skip_ir=SKIP_IR_RECEIVE,
                skip_debug=SKIP_DEBUG_PACK,
            )


# ---------------------------------------------------------------------------
# Pass 2 — per-stage time.monotonic() brackets
#
# WARNING: allocation/gc figures from this pass are DISTORTED — each
# time.monotonic() call allocates a heap float.  Use this pass only for a
# rough breakdown of where frame time goes, not for authoritative allocation
# or gc numbers.  Always run Pass 1 first for the trustworthy figures.
# ---------------------------------------------------------------------------


def _run_pass2(hw, manager, effect_manager, timer) -> None:  # type: ignore[no-untyped-def]
    """Pass 2: per-stage timers — distorted; orientation only."""
    perf = PerformanceTracker(log_interval=_LOG_INTERVAL)
    print_profile_header(
        component="scene_runtime.pass2_DISTORTED",
        sweep_axes=[
            "skip_gc",
            "skip_accel",
            "skip_ir",
            "skip_debug",
        ],
        sweep_values=[
            SKIP_GC_COLLECT,
            SKIP_ACCEL_READ,
            SKIP_IR_RECEIVE,
            SKIP_DEBUG_PACK,
        ],
        target_fps=0.0,
    )

    # Accumulators for per-stage totals (mutated in place, no per-frame alloc)
    t_buttons = 0.0
    t_accel = 0.0
    t_ir = 0.0
    t_queue = 0.0
    t_manager = 0.0
    t_effects = 0.0
    t_gc = 0.0
    n_frames = 0

    while True:
        perf.start_frame()
        t0 = time.monotonic()

        # Stage: button read
        button_data = hw.buttons.update(timer.elapsed)
        t1 = time.monotonic()

        # Stage: accelerometer read + AccelerationData alloc
        acceleration = None
        if not SKIP_ACCEL_READ and hw.accelerometer is not None:
            try:
                ax, ay, az = hw.accelerometer.acceleration
                acceleration = AccelerationData(ax, ay, az)
            except Exception:
                acceleration = None
        t2 = time.monotonic()

        # Stage: IR receive + IRReceived event queue
        active_state = manager.active_state
        if not SKIP_IR_RECEIVE and active_state is not None and hw.ir_receiver is not None:
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
        t3 = time.monotonic()

        # Stage: ButtonAndAcceleration event queue
        if active_state is not None:
            active_state.queue_event(InputEvents.ButtonAndAcceleration(button_data, acceleration))
        t4 = time.monotonic()

        # Stage: manager.update() — engine dispatch + scene transition check
        manager.update()
        t5 = time.monotonic()

        # Stage: effect_manager.update() — render + pixel write
        effect_manager.update(timer)
        t6 = time.monotonic()

        # Stage: gc.collect()
        if not SKIP_GC_COLLECT:
            gc.collect()
        t7 = time.monotonic()

        t_buttons += t1 - t0
        t_accel += t2 - t1
        t_ir += t3 - t2
        t_queue += t4 - t3
        t_manager += t5 - t4
        t_effects += t6 - t5
        t_gc += t7 - t6
        n_frames += 1

        if perf.complete_frame():
            n = n_frames if n_frames > 0 else 1
            print_stats_line(
                perf,
                skip_gc=SKIP_GC_COLLECT,
                skip_accel=SKIP_ACCEL_READ,
                skip_ir=SKIP_IR_RECEIVE,
                skip_debug=SKIP_DEBUG_PACK,
            )
            # Per-stage breakdown in seconds — printed separately so the
            # standard __STATS line is still machine-parseable.  The label
            # "DISTORTED" is a reminder that these figures include timer-float
            # allocation cost and are not authoritative.
            print(
                "__STAGES_DISTORTED"
                " buttons="
                + str(round(t_buttons / n, 6))
                + " accel="
                + str(round(t_accel / n, 6))
                + " ir="
                + str(round(t_ir / n, 6))
                + " queue="
                + str(round(t_queue / n, 6))
                + " manager="
                + str(round(t_manager / n, 6))
                + " effects="
                + str(round(t_effects / n, 6))
                + " gc="
                + str(round(t_gc / n, 6))
            )

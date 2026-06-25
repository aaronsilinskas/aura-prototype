"""End-to-end reference-prop profiler -- the real `tag` prop on an RP2040 PropMaker.

This is the measurement half of #401: it stands up the **whole** reference prop
(IS31FL3741 matrix, I2S audio, DRV2605L vibration, IR LINE emitter + one IR
receiver, two buttons) running the production `tag` scene -- the same wiring as
`examples/hardware/tag_demo.py` -- and reports the measured cost of running the
assembled prop on a single MCU (engine-host).

Unlike the per-component profilers under this directory (which isolate one cost
term each), this profiler measures the **assembled** prop end to end and reports:

- **CPU reservation %** -- the measured per-frame busy time (engine update +
  effect render+flush, sound, vibration) expressed as a percentage of the frame
  budget at `TARGET_FPS`.
- **Headroom %** -- the engine-host's usable budget
  (`100 - baseline_cpu_percent - headroom_reserve_percent`) minus the measured
  reservation.
- **Memory footprint (bytes)** -- the heap consumed standing the whole prop up,
  measured as a `gc.mem_free()` delta around setup.
- **Worst-case frame time (ms)** -- `PerformanceTracker.frame_time_peak`, the
  worst-case frame time the IR receiver's hard-real-time deadline is checked
  against. Exercise the prop (fire shots, take hits) to drive this peak.

The matrix flush (~60 ms) dominates the per-frame cost, so the prop cannot hold
24 FPS -- set `TARGET_FPS` to the rate the prop actually achieves (~11-13 FPS for
any IS31FL3741 scope). The profiler also reports its **measured** FPS so the
chosen budget can be sanity-checked against reality.

Hardware
--------
- Adafruit RP2040 PropMaker Feather
- Adafruit IS31FL3741 13x9 RGB LED Matrix Breakout (I2C on default SDA/SCL)
- Two buttons (pull-up) on BUTTON_A_PIN / BUTTON_B_PIN (default: D9 / D10)
- IR receiver on IR_RX_PIN; IR LINE emitter on IR_LINE_PIN
- DRV2605L haptic motor driver on default SDA/SCL (optional -- profiler runs
  without it, but the vibration component is then absent from the measurement)

Installation
------------
1. Install CircuitPython on your board:
   https://learn.adafruit.com/welcome-to-circuitpython/installing-circuitpython

2. Copy required libraries to CIRCUITPY/lib/:
     adafruit_is31fl3741/
     adafruit_drv2605.mpy  (optional - required only when a DRV2605L is wired up)

3. Run the deploy script to copy all source files and set code.py:
     python scripts/deploy.py examples/hardware/profiling/tag_prop_profiler.py
   The board reboots and starts running automatically.

How to use
----------
- Set `TARGET_FPS` to the prop's achievable tick rate (the frame budget the
  reservation/headroom percentages are computed against).
- With `AUTO_START = True` the profiler injects one synthetic button press at
  boot so the scene advances out of Ready into the Playing phase (the
  representative steady workload) without a human pressing a button.
- To drive the worst-case frame time, play the prop while it runs: press A to
  fire, and let it receive IR hits. The reported `peak_frame_ms` is a running
  maximum, so the highest spike over the whole run is retained.
- Read the paste-ready `__TABLE_ROW table=reference_prop_validation` line at each
  interval for the measured reference-prop metrics.

Configuration
-------------
- TARGET_FPS: frame budget basis for reservation/headroom (the prop's achievable
  rate, NOT the 24 FPS ceiling for any prop with a matrix scope).
- ENGINE_HOST_BASELINE_CPU_PERCENT / HEADROOM_RESERVE_PERCENT: the engine-host
  usable-budget terms used to derive measured headroom.
- AUTO_START: inject a synthetic press at boot to reach Playing automatically.
- LOG_INTERVAL_SECONDS: how often the stats line is printed.
"""

from __future__ import annotations

import gc
import time

import board

import hardware.circuitpython.propmaker as propmaker
from effects.performance import PerformanceTracker
from engine.audio import AudioRegistry
from engine.effects.manager import EffectManager
from engine.engine import GameEngine
from engine.input import AccelerationData, ButtonData, InputEvents
from engine.network import HardwareNetworkControls, NetworkEvents
from engine.packs import PackRegistry
from engine.scene import SceneManager, SceneRegistry
from engine.timer import Timer
from hardware.circuitpython.audio_output import AudioEffectOutput
from hardware.circuitpython.drv2605_output import Drv2605EffectOutput
from hardware.circuitpython.is31fl3741_output import (
    IS31FL3741_COLS,
    IS31FL3741_SCOPE_ROWS,
    IS31FL3741EffectOutput,
)
from hardware.shared.profiling_helpers import (
    print_profile_header,
    print_stats_line,
    print_table_row,
)
from hardware.shared.tag_protocol import TagInfraredDecoder, TagInfraredEncoder

try:
    from typing import Final
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Configuration -- adjust to match your wiring
# ---------------------------------------------------------------------------

BUTTON_A_PIN: Final = board.D9
BUTTON_B_PIN: Final = board.D10

# IR transceiver pins -- update these to match your board layout.
IR_RX_PIN: Final = board.D11
IR_LINE_PIN: Final = board.D12

# Frame budget basis. A prop with an IS31FL3741 scope cannot hold 24 FPS (the
# ~60 ms matrix flush alone exceeds the 41.7 ms budget), so reservation/headroom
# are computed against the rate the prop actually achieves. ~7 FPS is the rate
# this prop holds on a single MCU -- reconcile with the measured FPS.
TARGET_FPS: Final = 7.0

# Engine-host usable-budget terms (the per-MCU baseline CPU cost and the 20%
# default headroom reserve), used to derive the measured headroom percentage.
# These are the circuitpython_10_2_1 engine-host baseline; use 4.75 for 10_0_3.
ENGINE_HOST_BASELINE_CPU_PERCENT: Final = 5.65
HEADROOM_RESERVE_PERCENT: Final = 20.0

# Inject one synthetic button press at boot so the scene leaves Ready and enters
# Playing (the representative steady workload) without a human pressing a button.
AUTO_START: Final = True

# Discard the first `WARMUP_SECONDS` of measurement. Boot and the Ready->Starting
# ->Playing transitions *construct* effects across the matrix (palettes, LUTs,
# buffers) and open WAV files from flash for the first time -- one-time costs that
# spike a single frame into the hundreds of ms / ~1 s range. They are not the
# steady-state per-frame cost we want to measure, so the tracker is reset once
# warm-up elapses and only steady-state frames are reported.
WARMUP_SECONDS: Final = 10.0

LOG_INTERVAL_SECONDS: Final = 5.0


def _build_prop() -> tuple[SceneManager, EffectManager, Timer, object, object, object, int]:
    """Stand up the whole reference tag prop and return its driving objects.

    Snapshots free heap before and after construction (with a GC collect on each
    side so the figure is retained footprint, not transient construction litter)
    and returns the delta as the prop's measured `memory_footprint_bytes`.
    """
    gc.collect()
    free_before = gc.mem_free()

    propmaker.setup_external_power()
    i2c = propmaker.setup_i2c()
    matrix = propmaker.setup_matrix_is31fl3741(i2c)
    buttons = propmaker.setup_buttons(BUTTON_A_PIN, BUTTON_B_PIN)
    accelerometer = propmaker.setup_accelerometer(i2c)
    motor = propmaker.setup_drv2605(i2c)
    ir_transmitters, ir_receiver = propmaker.setup_ir(
        IR_RX_PIN,
        IR_LINE_PIN,
        encoder=TagInfraredEncoder(),
        decoder=TagInfraredDecoder(),
    )
    # Stage snapshot: hardware drivers (matrix/buttons/accel/motor/IR) on the heap.
    gc.collect()
    free_after_peripherals = gc.mem_free()

    effect_registry = PackRegistry(item_attr="BUILD")
    effect_registry.scan_dir("packs/effects", "packs.effects")
    rule_registry = PackRegistry(item_attr="RULE")
    rule_registry.scan_dir("packs/rules", "packs.rules")
    # Stage snapshot: scanned effect + rule pack registries (imported pack modules).
    gc.collect()
    free_after_registries = gc.mem_free()

    audio_registry = AudioRegistry()
    audio_registry.register("warning_pulse_peak", "sounds/blip.wav")
    audio_registry.register("game_over_sting_start", "sounds/game_over.wav")
    audio_registry.register("fire_shot_start", "sounds/blip.wav")
    audio_registry.register("scene.hit_start", "sounds/blip.wav")
    audio_registry.register("reload", "sounds/blip.wav")
    audio_registry.register("reload_complete", "sounds/blip.wav")

    audio_output = AudioEffectOutput(
        audio_registry,
        max_volume=0.1,
        num_voices=4,
        i2s_bit_clock=board.I2S_BIT_CLOCK,
        i2s_word_select=board.I2S_WORD_SELECT,
        i2s_data=board.I2S_DATA,
    )
    outputs = [
        IS31FL3741EffectOutput(matrix, cols=IS31FL3741_COLS, scope_rows=IS31FL3741_SCOPE_ROWS),
        audio_output,
    ]
    if motor is not None:
        outputs.append(Drv2605EffectOutput(motor))

    effect_manager = EffectManager(registry=effect_registry, outputs=outputs)
    # Stage snapshot: audio (registry + output) + EffectOutput wrappers + EffectManager.
    gc.collect()
    free_after_audio = gc.mem_free()

    # Own the Timer explicitly so the render phase can advance it without reaching
    # into GameEngine's internals (the engine advances this same instance in
    # update()). Passing it in keeps the profiler on the public API.
    timer = Timer()
    engine = GameEngine(
        effect_controls=effect_manager,
        timer=timer,
        network_controls=HardwareNetworkControls(ir_transmitters),
    )
    # Stage snapshot: Timer + GameEngine + HardwareNetworkControls.
    gc.collect()
    free_after_engine = gc.mem_free()

    scene_registry = SceneRegistry()
    scene_registry.scan_dir("packs/scenes", "packs.scenes")

    manager = SceneManager(engine, effect_registry, rule_registry, scene_registry)
    manager.load("tag")
    manager.update()  # applies the load transition; tag scene is now active

    gc.collect()
    free_after_scene = gc.mem_free()
    footprint_bytes = free_before - free_after_scene

    # Decompose the total footprint into construction stages so the ~32 KB can be
    # attributed (hardware components vs. the scanned pack registries vs. the loaded
    # scene), and cross-checked against the per-component profiler figures (#448).
    print(
        "__PROP_BREAKDOWN "
        f"peripherals={free_before - free_after_peripherals}, "
        f"registries={free_after_peripherals - free_after_registries}, "
        f"audio_outputs={free_after_registries - free_after_audio}, "
        f"engine={free_after_audio - free_after_engine}, "
        f"scene={free_after_engine - free_after_scene}"
    )
    return manager, effect_manager, timer, buttons, accelerometer, ir_receiver, footprint_bytes


def _press(name: str) -> ButtonData:
    """Build a one-frame synthetic press of `name` (the Ready->Starting trigger)."""
    return ButtonData({name: ButtonData.PRESSED})


def run() -> None:
    """Run the assembled tag prop end to end, reporting the #401 validation numbers."""
    (
        manager,
        effect_manager,
        timer,
        buttons,
        accelerometer,
        ir_receiver,
        footprint_bytes,
    ) = _build_prop()

    frame_budget_ms = 1000.0 / TARGET_FPS
    usable_cpu_percent = 100.0 - ENGINE_HOST_BASELINE_CPU_PERCENT - HEADROOM_RESERVE_PERCENT
    perf = PerformanceTracker(log_interval=LOG_INTERVAL_SECONDS)

    print_profile_header(
        component="tag_prop.end_to_end",
        sweep_axes=[],
        sweep_values=[],
        target_fps=TARGET_FPS,
    )
    print(f"__PROP footprint_bytes={footprint_bytes}, free_heap_bytes={gc.mem_free()}")

    start_injected = not AUTO_START
    warmup_done = WARMUP_SECONDS <= 0
    warmup_until = time.monotonic() + WARMUP_SECONDS

    while True:
        perf.start_frame()

        perf.start_update_time()
        elapsed = timer.elapsed

        button_data = buttons.update(elapsed)
        # One-time synthetic press to leave Ready without a human button press.
        if not start_injected:
            button_data = _press("A")
            start_injected = True

        if accelerometer is not None:
            try:
                ax, ay, az = accelerometer.acceleration
                acceleration = AccelerationData(ax, ay, az)
            except Exception:
                acceleration = None
        else:
            acceleration = None

        if manager.active_state is not None:
            ir_data = ir_receiver.receive()
            if ir_data is not None:
                manager.active_state.queue_event(
                    NetworkEvents.IRReceived(
                        ir_data,
                        ir_receiver.last_signal_strength,
                        ir_receiver.last_error_margin,
                        best_receiver=None,
                    )
                )
            manager.active_state.queue_event(
                InputEvents.ButtonAndAcceleration(button_data, acceleration)
            )

        manager.update()
        perf.add_update_time()

        perf.start_render_time()
        effect_manager.update(timer)
        perf.add_render_time()

        if not perf.complete_frame():
            continue

        # Drop the warm-up window: boot + scene transitions construct effects and
        # open WAV files for the first time, spiking single frames into the
        # hundreds of ms / ~1 s range. Reset the tracker once so averages and the
        # peak reflect only steady-state frames, not one-time construction cost.
        if not warmup_done and time.monotonic() >= warmup_until:
            warmup_done = True
            perf = PerformanceTracker(log_interval=LOG_INTERVAL_SECONDS)
            print(f"__WARMUP_DONE after {WARMUP_SECONDS:.0f}s; measuring steady state")
            continue
        if not warmup_done:
            continue

        frames = perf.frame_count
        update_ms = perf.update_time_total / frames * 1000.0
        render_ms = perf.render_time_total / frames * 1000.0
        busy_ms = update_ms + render_ms
        reservation_percent = busy_ms / frame_budget_ms * 100.0
        headroom_percent = usable_cpu_percent - reservation_percent
        # Windowed peak: the worst frame in *this* interval. Reset below so a lone
        # transient (e.g. a first-time WAV load) shows only in its own interval
        # rather than pinning the figure for the rest of the run.
        peak_frame_ms = perf.frame_time_peak * 1000.0

        print_stats_line(
            perf,
            update_ms=f"{update_ms:.4f}",
            render_ms=f"{render_ms:.4f}",
            reservation=f"{reservation_percent:.2f}%",
            headroom=f"{headroom_percent:.2f}%",
        )
        # Measured reference-prop metrics (#401).
        print_table_row(
            "reference_prop_validation",
            [
                f"{reservation_percent:.2f}%",
                footprint_bytes,
                f"{headroom_percent:.2f}%",
                f"{peak_frame_ms:.4f}",
            ],
        )
        perf.frame_time_peak = 0.0


run()

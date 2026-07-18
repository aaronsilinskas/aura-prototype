"""End-to-end reference-prop profiler -- the real `tag` prop on an RP2040 PropMaker.

This is the measurement half of #401: it stands up the **whole** reference prop
(IS31FL3741 matrix, I2S audio, DRV2605L haptic, IR LINE emitter + one IR
receiver, two buttons) running the production `tag` scene -- the same wiring as
`examples/hardware/tag_demo.py` -- and reports the measured cost of running the
assembled prop on a single MCU (engine-host).

Unlike the per-component profilers under this directory (which isolate one cost
term each), this profiler measures the **assembled** prop end to end and reports:

- **CPU reservation %** -- the measured per-frame busy time (engine update +
  effect render+flush, sound, haptic) expressed as a percentage of the frame
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

Hardware bring-up
------------------
The whole hardware bundle -- matrix, buttons, accelerometer, haptic driver, audio,
and IR -- is brought up through a single `build_hardware` call from the **real**,
deployed `aura-device.json` (`load_device_config()`) -- the config-driven model
#686 established for the scene-load profiler, and the same file
`examples/hardware/tag_demo.py` runs against. Unlike the per-component
profilers under this directory, nothing is muted here: this profiler validates
the **assembled** reference prop end to end, so every section the deployed
config declares (pixels, buttons, `ir`, `audio`, `accelerometer`, `haptics`) is
left exactly as declared and enabled -- there is no private harness mapping,
no hardcoded pixel/audio geometry or I2S pins, and no pins harvested and
re-assembled by hand. A declared `accelerometer`/`haptics` section whose chip
can't be found on the bus raises (config-gated, not presence-probed, per
#691) rather than silently degrading the measurement -- so, as with
`scene_load_profiler.py`, **the deployed config must actually describe the
reference `tag` prop**: `_build_prop` asserts the matrix, audio, haptic driver,
accelerometer, and IR receiver all came back in the built bundle, so a config
missing (or disabling) one of those sections fails loudly at bring-up rather
than reporting an incomplete measurement.

Hardware
--------
- Adafruit RP2040 PropMaker Feather (onboard LIS3DH accelerometer)
- Adafruit IS31FL3741 13x9 RGB LED Matrix Breakout (I2C on default SDA/SCL)
- Two buttons (pull-up), wired to the pins declared as `buttons[0]` /
  `buttons[1]` in `aura-device.json`
- IR receiver and IR LINE emitter, wired to the pins declared as `ir.rx` /
  `ir.line` in `aura-device.json`
- DRV2605L haptic driver on default SDA/SCL -- required, since the
  deployed config must declare a `haptics` section; a missing driver makes the
  build raise instead of silently dropping haptic output from the measurement

Installation
------------
1. Install CircuitPython on your board:
   https://learn.adafruit.com/welcome-to-circuitpython/installing-circuitpython

2. Copy required libraries to CIRCUITPY/lib/:
     adafruit_is31fl3741/
     adafruit_lis3dh.mpy
     adafruit_drv2605.mpy

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
- aura-device.json: the single source of truth for the whole assembled reference prop
  -- pixels, buttons, IR, audio, accelerometer, and haptics. Edit it, not this file, to
  change the prop's wiring; a section this profiler expects to find missing or disabled
  fails loudly at bring-up.
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

from effects.performance import PerformanceTracker
from engine.effects.manager import EffectManager
from engine.effects.output import EffectOutput
from engine.engine import GameEngine
from engine.input import AccelerationData, ButtonData, InputEvents
from engine.network import NetworkEvents
from engine.packs import PackRegistry
from engine.scene import SceneManager, SceneRegistry
from engine.timer import Timer
from hardware.circuitpython.audio_output import AudioEffectOutput
from hardware.circuitpython.device_builder import build_hardware
from hardware.circuitpython.drv2605_output import Drv2605EffectOutput
from hardware.circuitpython.is31fl3741_output import IS31FL3741EffectOutput
from hardware.shared.device_config import load_device_config
from hardware.shared.device_hardware import DeviceHardware
from hardware.shared.network_controls import HardwareNetworkControls
from hardware.shared.profiler_report import (
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


def _require_output(hardware: DeviceHardware, output_type: type[EffectOutput]) -> None:
    """Raise loudly if no *output_type* instance is present in the built bundle.

    `build_hardware` is config-gated for pixels/audio/IR, so a deployed config
    declaring all three should always yield them -- a missing one signals the
    deployed `aura-device.json` doesn't actually describe the reference `tag`
    prop this profiler measures, which would otherwise show up only as a
    silently incomplete measurement.
    """
    if not any(isinstance(output, output_type) for output in hardware.outputs):
        raise RuntimeError(
            f"expected a {output_type.__name__} in the built hardware bundle, found none"
        )


def _build_prop() -> tuple[
    SceneManager, EffectManager, Timer, object, object, object, HardwareNetworkControls, int
]:
    """Stand up the whole reference tag prop and return its driving objects.

    Snapshots free heap before and after construction (with a GC collect on each
    side so the figure is retained footprint, not transient construction litter)
    and returns the delta as the prop's measured `memory_footprint_bytes`.
    """
    gc.collect()
    free_before = gc.mem_free()

    # Stand up the whole prop from the real, deployed aura-device.json -- no private
    # harness mapping, no harvested pins re-assembled by hand. Whatever the config
    # declares (pixels, buttons, ir, audio, accelerometer, haptics) is exactly what
    # gets built; the assertions below fail loudly if the deployed config doesn't
    # actually describe the reference tag prop this profiler measures.
    device_config = load_device_config()
    hardware = build_hardware(
        device_config,
        board,
        ir_encoder=TagInfraredEncoder(),
        ir_decoder=TagInfraredDecoder(),
    )
    _require_output(hardware, IS31FL3741EffectOutput)
    _require_output(hardware, AudioEffectOutput)
    _require_output(hardware, Drv2605EffectOutput)
    if hardware.ir_receiver is None:
        raise RuntimeError("expected an IR receiver in the built hardware bundle, found none")
    if hardware.accelerometer is None:
        raise RuntimeError("expected an accelerometer in the built hardware bundle, found none")
    # Stage snapshot: the whole hardware bundle (matrix, buttons, accelerometer,
    # haptic driver, audio, IR) brought up through the single build_hardware call.
    gc.collect()
    free_after_hardware = gc.mem_free()

    effect_registry = PackRegistry(item_attr="BUILD")
    effect_registry.scan_dir("packs/effects", "packs.effects")
    rule_registry = PackRegistry(item_attr="RULE")
    rule_registry.scan_dir("packs/rules", "packs.rules")
    # Stage snapshot: scanned effect + rule pack registries (imported pack modules).
    gc.collect()
    free_after_registries = gc.mem_free()

    effect_manager = EffectManager(registry=effect_registry, outputs=hardware.outputs)
    # Stage snapshot: EffectManager wrapping the bundle's outputs -- the one piece
    # of construction downstream of build_hardware that the profiler still owns
    # (the audio/matrix/haptic driver hardware itself is now inside the bundle above).
    gc.collect()
    free_after_effect_manager = gc.mem_free()

    # Own the Timer explicitly so the render phase can advance it without reaching
    # into GameEngine's internals (the engine advances this same instance in
    # update()). Passing it in keeps the profiler on the public API.
    timer = Timer()
    engine = GameEngine(
        effect_controls=effect_manager,
        timer=timer,
        network_controls=hardware.network_controls,
    )
    # Stage snapshot: Timer + GameEngine.
    gc.collect()
    free_after_engine = gc.mem_free()

    scene_registry = SceneRegistry()
    scene_registry.scan_dir("packs/scenes", "packs.scenes")

    manager = SceneManager(
        engine, effect_registry, rule_registry, scene_registry, effect_admin=effect_manager
    )
    manager.load("tag")
    manager.update()  # applies the load transition; tag scene is now active

    gc.collect()
    free_after_scene = gc.mem_free()
    footprint_bytes = free_before - free_after_scene

    # Decompose the total footprint into construction stages so the ~32 KB can be
    # attributed (the hardware bundle vs. the scanned pack registries vs. the
    # EffectManager wrap vs. the engine vs. the loaded scene), and cross-checked
    # against the per-component profiler figures (#448). The hardware bundle is
    # now one delta -- build_hardware's single call is the coarsest boundary the
    # profiler can measure across.
    print(
        f"__PROP_BREAKDOWN hardware={free_before - free_after_hardware}, "
        + f"registries={free_after_hardware - free_after_registries}, "
        + f"effect_manager={free_after_registries - free_after_effect_manager}, "
        + f"engine={free_after_effect_manager - free_after_engine}, "
        + f"scene={free_after_engine - free_after_scene}"
    )
    return (
        manager,
        effect_manager,
        timer,
        hardware.buttons,
        hardware.accelerometer,
        hardware.ir_receiver,
        hardware.network_controls,
        footprint_bytes,
    )


def _inject_press(name: str, out: ButtonData) -> None:
    """Inject the Ready->Starting trigger without a human button press."""
    out.set(name, ButtonData.PRESSED)


def run() -> None:
    """Run the assembled tag prop end to end, reporting the #401 validation numbers."""
    (
        manager,
        effect_manager,
        timer,
        buttons,
        accelerometer,
        ir_receiver,
        network_controls,
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

    _button_data = ButtonData({})
    _acceleration = AccelerationData(0.0, 0.0, 0.0) if accelerometer is not None else None
    _input_event = InputEvents.ButtonAndAcceleration(_button_data, _acceleration)

    start_injected = not AUTO_START
    warmup_done = WARMUP_SECONDS <= 0
    warmup_until = time.monotonic() + WARMUP_SECONDS

    while True:
        perf.start_frame()

        perf.start_update_time()
        elapsed = timer.elapsed

        buttons.update(elapsed, _button_data)
        # One-time synthetic press to leave Ready without a human button press.
        if not start_injected:
            _inject_press("A", _button_data)
            start_injected = True

        if _acceleration is not None:
            try:
                ax, ay, az = accelerometer.acceleration
                _acceleration.x = ax
                _acceleration.y = ay
                _acceleration.z = az
            except Exception:
                pass  # keep last good values

        # Outside the active_state guard and before receive(): a send can be
        # in flight across a scene transition, and end_transmit (fired here
        # when a deferred write completes) arms the flush latch this same
        # tick's receive() must consume.
        network_controls.poll_transmits()

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
            manager.active_state.queue_event(_input_event)

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

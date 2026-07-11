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

Hardware bring-up
------------------
The whole hardware bundle -- matrix, buttons, accelerometer/motor (probed by
physical presence), audio, and IR -- is brought up through a single
`build_hardware` call, from a `DeviceConfig` built in-file (see
`_build_tag_harness` below). Button and IR wiring pins (`buttons[0]`,
`buttons[1]`, `ir.rx`, `ir.line`) are sourced from the real `aura-device.json`
on the CIRCUITPY drive via `load_device_config()`/`require_pin`, so the
profiler's button/IR wiring never drifts from the on-device config; a pin
absent from `aura-device.json` fails loudly with a "not declared" error rather
than falling back to a guessed pin. The pixel/audio harness sections
(clips/voices/codec) stay profiler-owned and hardcoded, as do the I2S bus pins
(they have no schema field here -- see the Handoff in #646).

Hardware
--------
- Adafruit RP2040 PropMaker Feather
- Adafruit IS31FL3741 13x9 RGB LED Matrix Breakout (I2C on default SDA/SCL)
- Two buttons (pull-up), wired to the pins declared as `buttons[0]` /
  `buttons[1]` in `aura-device.json`
- IR receiver and IR LINE emitter, wired to the pins declared as `ir.rx` /
  `ir.line` in `aura-device.json`
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
- buttons[0] / buttons[1] / ir.rx / ir.line: read from `aura-device.json` (via
  `require_pin`) -- the button and IR wiring pins for the reference prop. A
  missing pin fails loudly.
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
from hardware.circuitpython.is31fl3741_output import IS31FL3741EffectOutput
from hardware.shared.device_config import load_device_config, parse_device_config, require_pin
from hardware.shared.device_hardware import DeviceHardware
from hardware.shared.network_controls import HardwareNetworkControls
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

# I2S amp pins -- update these to match your board layout. Declared directly
# in _build_tag_harness's audio section below, resolved against the real
# `board` module by build_hardware the same way every other configured pin
# is. No aura-device.json schema field owns these here -- see the Handoff
# in #646.
I2S_BIT_CLOCK_PIN_NAME: Final = "GP10"
I2S_WORD_SELECT_PIN_NAME: Final = "GP11"
I2S_DATA_PIN_NAME: Final = "GP12"

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


def _build_tag_harness(
    button_a_pin: str, button_b_pin: str, ir_rx_pin: str, ir_line_pin: str
) -> dict:
    """Return the aura-device.json-shaped mapping for the reference tag prop.

    *button_a_pin*, *button_b_pin*, *ir_rx_pin*, and *ir_line_pin* are real pin
    names harvested from `aura-device.json` by `_build_prop()` via `require_pin`
    (`buttons[0]`, `buttons[1]`, `ir.rx`, `ir.line`) -- a missing one fails
    loudly there rather than falling back to a guessed pin.

    The pixels/audio sections stay profiler-owned and hardcoded here, mirroring
    `examples/hardware/tag_demo.py`'s pixel wiring, plus 4 audio voices covering
    the 7 clips this profiler has historically exercised (carried over unchanged
    from the pre-migration setup) -- a subset of the `tag` scene's full clip
    set; `dry_fire_start` and `ready_shots_start` are not included. The I2S bus
    pins likewise stay hardcoded -- they have no schema field here and are owned
    by the I2S spec (see the Handoff in #646).
    """
    return {
        "pixels": [
            {
                "type": "matrix",
                "cols": 13,
                "scope_rows": {
                    "global.buff": [0, 1],
                    "global.debuff": [1, 2],
                    "global.main": [2, 5],
                    "personal": [5, 7],
                    "directional": [7, 8],
                    "ambient": [8, 9],
                },
            }
        ],
        "buttons": [button_a_pin, button_b_pin],
        "ir": {"rx": ir_rx_pin, "line": ir_line_pin},
        "audio": {
            "voices": 4,
            "max_volume": 0.1,
            "clips": {
                "warning_pulse_peak": "sounds/blip.wav",
                "go_start": "sounds/blip.wav",
                "game_over_sting_start": "sounds/game_over.wav",
                "fire_shot_start": "sounds/blip.wav",
                "scene.hit_start": "sounds/blip.wav",
                "reload": "sounds/blip.wav",
                "reload_complete": "sounds/blip.wav",
            },
            "i2s_bit_clock": I2S_BIT_CLOCK_PIN_NAME,
            "i2s_word_select": I2S_WORD_SELECT_PIN_NAME,
            "i2s_data": I2S_DATA_PIN_NAME,
        },
    }


def _require_output(hardware: DeviceHardware, output_type: type[EffectOutput]) -> None:
    """Raise loudly if no *output_type* instance is present in the built bundle.

    `build_hardware` is config-gated for pixels/audio/IR, so a harness that
    declares all three should always yield them -- a missing one signals the
    harness and the bundle have drifted apart, which would otherwise show up
    only as a silently incomplete measurement.
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

    # Harvest button/IR wiring pins from the real aura-device.json -- never fed
    # wholesale to build_hardware below, only used as a pin-name source for the
    # in-file _build_tag_harness mapping (pixels/audio sections stay
    # profiler-owned). A pin absent from aura-device.json fails loudly here.
    device_config = load_device_config()
    button_a_pin = require_pin(device_config, lambda c: c.buttons[0], "buttons[0]")
    button_b_pin = require_pin(device_config, lambda c: c.buttons[1], "buttons[1]")
    ir_rx_pin = require_pin(device_config, lambda c: c.ir.rx, "ir.rx")
    ir_line_pin = require_pin(device_config, lambda c: c.ir.emitters["line"], "ir.line")

    config = parse_device_config(
        _build_tag_harness(button_a_pin, button_b_pin, ir_rx_pin, ir_line_pin)
    )
    hardware = build_hardware(
        config,
        board,
        ir_encoder=TagInfraredEncoder(),
        ir_decoder=TagInfraredDecoder(),
        i2c=board.STEMMA_I2C(),
    )
    _require_output(hardware, IS31FL3741EffectOutput)
    _require_output(hardware, AudioEffectOutput)
    if hardware.ir_receiver is None:
        raise RuntimeError("expected an IR receiver in the built hardware bundle, found none")
    # Stage snapshot: the whole hardware bundle (matrix, buttons, accelerometer,
    # motor, audio, IR) brought up through the single build_hardware call.
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
    # (the audio/matrix/motor hardware itself is now inside the bundle above).
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

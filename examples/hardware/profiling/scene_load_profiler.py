"""In-situ scene-load profiler -- staged `load` / first-tick heap on the deployed prop.

This is the diagnostic half of the capacity teardown (#460): it stands up **whatever
prop the deployed ``aura-device.json`` describes** -- the same
``read_device_config_mapping`` -> ``parse_device_config`` -> ``build_hardware`` path
``examples/hardware/scene_demo.py`` drives via ``app.scene_runtime.run_scene`` -- loads
the scene the config names, and reports the heap consumed in two headline stages (see
"Hardware bring-up" below for the finer breakdown the ``__SCENE_STAGES`` line prints
around them):

- **`load` delta** -- the heap ``SceneManager.load(scene_name)`` retains: the scene
  graph (phases, rules, effects) instantiated against the prop's registered scopes.
- **first-tick delta** -- the heap the first ``SceneManager.update()`` retains: the
  load transition is applied and the scene's opening effects fire for the first
  time (palettes/LUTs/buffers constructed, WAV files opened from flash).

Scene memory is **output-coupled** (the one #450 finding whose mechanism did not
survive but whose effect did), so a headless load -- against a `NullEffectOutput`
with no matrix buffers and no audio -- reports a different, misleading figure (the
old `baseline_profiler.py` `scene_content` mode produced a ~2x number and has been
removed). This profiler exists to measure the scene **in situ**, on the prop it
actually runs on.

What this tool is and is NOT
----------------------------
This is a **per-prop, scene-parameterized diagnostic** -- a tool for A/B comparing a
scene change against that scene's recorded baseline. It is **not** a feasibility
tool: it does not answer "will the prop fit". Only the whole-prop run
(`tag_prop_profiler.py`) answers that, because the parts do not sum to the whole.

!! THE DEPLOYED CONFIG MUST MATCH THE SCENE !!
-----------------------------------------------
A recorded figure is valid **only for the `(scene, config)` pair it was measured
against.** The deployed ``aura-device.json`` -- which pixels/audio/IR sections are
present, which audio clips are registered, how many voices -- is the **single source
of truth** for the whole prop; this profiler carries no private wiring of its own and
does not auto-derive a scene's needs from the scene itself. To measure a scene under a
different harness, deploy a different ``aura-device.json`` that registers the scene's
clips and wires its scopes -- the same contract production ``run_scene`` requires, not
an in-file table to hand-edit.

Loading a scene against a mismatched config (missing its audio clips, or missing its
targeted scopes/outputs) reproduces the exact headless-style artifact that motivated
this teardown: effects fail to resolve, and the first-tick allocation is wrong. If you
add or change a scene's clips/scopes, update the deployed ``aura-device.json`` to
match, and re-record its baseline -- an old figure measured against a different config
is not comparable.

This profiler registers no clip/scope guard of its own: registering the scene's clips
is the deployer's responsibility, the same contract ``build_hardware``/``run_scene``
apply in production. A config with an ``ir`` section but no ``line`` emitter wires a
receiver and no LINE emitter silently -- accepted here, exactly as it is in production.

Hardware bring-up
------------------
``build_hardware(config)`` is called with **no** codec argument -- the default Aura
wire-frame -- the same seam ``run_scene`` uses. The profiler asserts nothing about
which outputs the assembled bundle contains, which is what enables the "disable a
hardware section in the config and re-run to see its heap impact" workflow: comment out
`audio` or `ir` in the deployed ``aura-device.json`` and re-run to see the corresponding
shift in the ``__SCENE_STAGES`` breakdown.

Hardware
--------
This measures scene heap against whatever outputs the deployed ``aura-device.json``
declares; it does not read buttons or the accelerometer (inputs do not allocate scene
heap), even though ``build_hardware`` wires them up when their sections are declared.
Hardware present in practice: an Adafruit RP2040 PropMaker Feather, an Adafruit
IS31FL3741 13x9 RGB LED Matrix Breakout (I2C on default or configured SDA/SCL), and
optionally a DRV2605L haptic motor driver (config-gated by a ``haptics`` section -- the
profiler runs without one declared, but the vibration output is then absent from the
measurement).

Installation
------------
1. Install CircuitPython on your board:
   https://learn.adafruit.com/welcome-to-circuitpython/installing-circuitpython

2. Copy required libraries to CIRCUITPY/lib/ matching the sections your
   ``aura-device.json`` declares, e.g.:
     adafruit_is31fl3741/
     adafruit_lis3dh.mpy
     adafruit_drv2605.mpy  (optional - required only when a DRV2605L is wired up)

3. Deploy an ``aura-device.json`` naming the scene to measure (top-level ``"scene"``
   key) and registering that scene's clips/scopes -- see
   ``examples/aura-device.sample.json``. The file is required; a missing, invalid, or
   unregistered-scene config fails loudly at import time, naming the known scenes.

4. Run the deploy script to copy all source files and set code.py:
     python scripts/deploy.py examples/hardware/profiling/scene_load_profiler.py
   The board reboots and starts running automatically.

How to use
----------
- Set the deployed ``aura-device.json``'s top-level ``"scene"`` key to the scene you
  want to measure -- CircuitPython has no argv, so the deployed config is the only
  per-boot selector. A scene name absent from the scanned scene registry fails loud,
  naming the known scenes.
- Confirm the deployed config registers that scene's clips and wires the scopes/outputs
  it targets -- an under-configured prop reproduces the headless-style artifact this
  profiler exists to catch.
- Read the ``__SCENE_STAGES`` line for the staged free-heap breakdown and the
  ``__TABLE_ROW table=scene_in_situ_baselines`` line for the paste-ready row to
  record in ``docs/hardware/recorded-metrics.md``.

Configuration
-------------
- aura-device.json: the single source of truth for both the prop under test and the
  scene to measure (its ``"scene"`` key). Edit it, not this file, to change what is
  measured.
- LOG_INTERVAL_SECONDS: how often the post-load stats line is printed.
"""

from __future__ import annotations

import gc

from effects.performance import PerformanceTracker
from engine.effects.manager import EffectManager
from engine.engine import GameEngine
from engine.packs import PackRegistry
from engine.scene import SceneManager, SceneRegistry
from engine.timer import Timer
from hardware.circuitpython.device_builder import build_hardware
from hardware.circuitpython.drv2605_output import Drv2605EffectOutput
from hardware.shared.device_config import (
    DeviceConfig,
    parse_device_config,
    read_device_config_mapping,
)
from hardware.shared.profiling_helpers import (
    metrics_harness_label,
    print_profile_header,
    print_stats_line,
    print_table_row,
)
from hardware.shared.scene_selection import resolve_scene_name

try:
    from typing import Final
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Configuration -- how often the post-load stats line is printed. Everything
# else this profiler measures comes from the deployed aura-device.json.
# ---------------------------------------------------------------------------

LOG_INTERVAL_SECONDS: Final = 5.0


def _resolve_known_scene(scene_registry: SceneRegistry, scene_name: str) -> str:
    """Return *scene_name* if registered, else raise naming the known scenes.

    Mirrors ``app.scene_composition._resolve_known_scene`` (#684). This profiler
    keeps its own inlined staged composition rather than delegating to
    ``build_scene_runtime``, so it re-applies the same fail-loud rule -- no silent
    fallback -- against its own scanned scene registry instead of inheriting it.
    """
    names = scene_registry.names()
    if scene_name in names:
        return scene_name
    raise ValueError(f"unknown scene {scene_name!r}; known scenes: {', '.join(names)}")


def _build_prop(scene_name: str, config: DeviceConfig) -> tuple[SceneManager, EffectManager, Timer]:
    """Stand up the deployed prop and load *scene_name* in situ.

    Brings hardware up via the single ``build_hardware(config)`` call -- the same
    seam ``run_scene`` uses, with no codec argument (default Aura wire-frame) -- then
    loads the scene against those real outputs and applies its first tick. Prints the
    staged ``__SCENE_STAGES`` breakdown plus the paste-ready ``scene_in_situ_baselines``
    row. Returns the live driving objects so the caller can keep ticking the scene for
    observation.
    """
    gc.collect()
    free_before_hardware = gc.mem_free()
    hw = build_hardware(config)
    gc.collect()
    free_after_hardware = gc.mem_free()

    effect_registry = PackRegistry(item_attr="BUILD")
    effect_registry.scan_dir("packs/effects", "packs.effects")
    rule_registry = PackRegistry(item_attr="RULE")
    rule_registry.scan_dir("packs/rules", "packs.rules")
    scene_registry = SceneRegistry()
    scene_registry.scan_dir("packs/scenes", "packs.scenes")
    gc.collect()
    free_after_registries = gc.mem_free()

    effect_manager = EffectManager(registry=effect_registry, outputs=hw.outputs)
    timer = Timer()
    engine = GameEngine(
        effect_controls=effect_manager,
        timer=timer,
        network_controls=hw.network_controls,
    )
    manager = SceneManager(
        engine, effect_registry, rule_registry, scene_registry, effect_admin=effect_manager
    )
    gc.collect()
    free_after_engine = gc.mem_free()

    manager.load(_resolve_known_scene(scene_registry, scene_name))
    gc.collect()
    free_after_load = gc.mem_free()

    manager.update()  # applies the load transition; the scene's first tick fires
    gc.collect()
    free_after_tick = gc.mem_free()

    hardware_bytes = free_before_hardware - free_after_hardware
    registries_bytes = free_after_hardware - free_after_registries
    engine_bytes = free_after_registries - free_after_engine
    load_bytes = free_after_engine - free_after_load
    first_tick_bytes = free_after_load - free_after_tick
    motor_present = any(isinstance(output, Drv2605EffectOutput) for output in hw.outputs)

    print(
        f"__SCENE_STAGES scene={scene_name}, motor_present={motor_present}, "
        + f"hardware={hardware_bytes}, registries={registries_bytes}, "
        + f"engine={engine_bytes}, load={load_bytes}, first_tick={first_tick_bytes}, "
        + f"free_after_tick={free_after_tick}"
    )
    # Per-scene in-situ baseline: the (scene, config) pair, its staged `load`
    # heap, and its first-tick heap. A standalone measurement -- not an additive
    # term, valid only for this pairing.
    print_table_row(
        "scene_in_situ_baselines",
        [scene_name, metrics_harness_label(config), load_bytes, first_tick_bytes],
    )
    return manager, effect_manager, timer


def run() -> None:
    """Measure the deployed config's scene in-situ load/first-tick heap, then keep ticking."""
    mapping = read_device_config_mapping()
    config = parse_device_config(mapping)
    scene_name = resolve_scene_name(mapping)

    print_profile_header(
        component=f"scene_load.{scene_name}",
        sweep_axes=[],
        sweep_values=[],
        target_fps=0.0,
    )

    manager, effect_manager, timer = _build_prop(scene_name, config)
    perf = PerformanceTracker(log_interval=LOG_INTERVAL_SECONDS)

    # The measurement is complete; the loop just keeps the scene live so the run
    # is observable (free heap holds steady, the device does not idle into a hang).
    while True:
        perf.start_frame()

        perf.start_update_time()
        timer.update()
        manager.update()
        effect_manager.update(timer)
        perf.add_update_time()

        if perf.complete_frame():
            print_stats_line(perf)


run()

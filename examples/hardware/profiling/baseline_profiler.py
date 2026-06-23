"""CircuitPython baseline profiler — measures each board's fixed framework tax.

Runs the framework loop with zero rules, zero registered effect packs, and
zero components, so the reported FPS/CPU/heap numbers represent the cost of
the engine itself before any component-specific work is added. Every other
profiler under ``examples/hardware/profiling/`` should be compared against
this baseline.

Three modes are available — set ``MODE`` below:

- ``"engine_host"`` — the framework loop driving ``GameEngine.update`` with an
  ``EffectManager`` that has no registered outputs and no rules. Models a
  device that owns game logic but renders nothing itself (e.g. a controller).
- ``"satellite"`` — the framework loop driving an ``EffectManager`` with a
  no-op ``EffectOutput`` (command-receive scaffold, no pixels, no rules, no
  components). Models a device that only receives effect commands and would
  normally drive hardware outputs.
- ``"scene_content"`` — scans the real effect/rule/scene packs and loads
  ``SCENE_NAME`` **headless** (a ``NullEffectOutput``, no hardware), measuring
  the heap the loaded scene graph consumes. This is the per-scene content term
  the capacity model lacks (#448): it isolates the scene's rules/effects/phases
  from the hardware-coupled pixel buffers (which a `NullEffectOutput` never
  allocates), so the assembled prop's dominant "scene" heap can be split into
  hardware-independent scene content vs. matrix pixel buffers.

All modes print the shared profiling header once at startup and the uniform
stats line every ``LOG_INTERVAL_SECONDS``.

Hardware
--------
- Any CircuitPython-compatible board. No additional wiring is required — this
  profiler does not drive any LEDs or other peripherals.

Installation
------------
1. Install CircuitPython on your board:
   https://learn.adafruit.com/welcome-to-circuitpython/installing-circuitpython

2. Run the deploy script to copy all source files and set code.py:
     python scripts/deploy.py examples/hardware/profiling/baseline_profiler.py
   The board reboots and starts running automatically.

Configuration
-------------
- MODE: "engine_host", "satellite", or "scene_content"
- SCENE_NAME: scene loaded headless in "scene_content" mode
- BALLAST_BYTES: "scene_content" investigation knob -- pre-allocate heap to shrink
  free memory at load time (the #448 allocation-context test; 0 = off)
- TARGET_FPS: informational only — included in the header for comparison
  against component profilers with real per-frame work
- LOG_INTERVAL_SECONDS: how often the stats line is printed
"""

from __future__ import annotations

import gc

from effects.performance import PerformanceTracker
from engine.effects.manager import EffectManager, EffectOutput
from engine.engine import GameEngine
from engine.packs import PackRegistry
from engine.scene import SceneManager, SceneRegistry
from engine.state import GameState, SceneControls
from engine.timer import Timer
from hardware.shared.profiling_helpers import (
    print_profile_header,
    print_stats_line,
    print_table_row,
)

try:
    from typing import Final
except ImportError:
    pass

MODE: Final = "engine_host"  # or "satellite" or "scene_content"
TARGET_FPS: Final = 24.0
LOG_INTERVAL_SECONDS: Final = 5.0

# Scene loaded headless in "scene_content" mode (the reference prop runs "tag").
SCENE_NAME: Final = "tag"

# Investigation knob (#448): pre-allocate this many bytes of ballast before loading the
# scene, held alive but excluded from the deltas, to shrink the free heap at load time.
# The headless scene-load heap (~34 KB) came out larger than its in-situ contribution
# (~19 KB), where the scene loads with ~60 KB less free heap. If raising BALLAST_BYTES
# shrinks the measured scene heap toward the in-situ figure, the gap is allocation
# context (free-heap-dependent GC retention), not a different object graph. The #448
# investigation found it is NOT context (ballast barely moved it) -- left at 0; see the
# "Scene-content memory" note in the capacity doc.
BALLAST_BYTES: Final = 0


class NullEffectOutput(EffectOutput):
    """Command-receive scaffold for satellite mode: no pixels, no hardware writes.

    Registers no scopes, so ``EffectManager`` never routes effects to it; it
    exists purely to model the per-tick cost of having an output registered
    (the ``flush`` call every tick) without any pixel buffers or hardware I/O.
    """

    def __init__(self) -> None:
        super().__init__(receives_pixels=False)
        self.min_resolution = 0
        self.scopes = []


def _heap_tax(mem_free_before: int) -> int:
    """Heap consumed since ``mem_free_before`` was snapshotted.

    Collects garbage first so the figure is the framework's retained tax (the
    `heap_bytes` column of the Per-MCU baselines table), not transient
    construction litter.
    """
    gc.collect()
    return mem_free_before - gc.mem_free()


def _build_engine_host() -> tuple[EffectManager, GameEngine, GameState, int]:
    gc.collect()
    mem_free_before = gc.mem_free()
    registry = PackRegistry(item_attr="BUILD")
    effect_manager = EffectManager(registry=registry, outputs=[])
    game_engine = GameEngine(effect_controls=effect_manager)
    game_state = game_engine.create_state(SceneControls())
    return effect_manager, game_engine, game_state, _heap_tax(mem_free_before)


def _build_satellite() -> tuple[EffectManager, int]:
    gc.collect()
    mem_free_before = gc.mem_free()
    registry = PackRegistry(item_attr="BUILD")
    effect_manager = EffectManager(registry=registry, outputs=[NullEffectOutput()])
    return effect_manager, _heap_tax(mem_free_before)


def _build_scene_content() -> tuple[SceneManager, EffectManager, Timer, int, int]:
    """Scan the real packs and load ``SCENE_NAME`` headless, splitting the heap.

    Mirrors the tag prop's logic stack (`tag_prop_profiler._build_prop`) but with a
    `NullEffectOutput` and no hardware, so the scene graph is instantiated without the
    matrix pixel buffers. Returns the registry-scan heap and the scene-load heap
    separately: the scan registers cheap factory callables, while `load` + `update`
    instantiate the phases/rules/effects -- the per-scene content term the model lacks.
    """
    # Ballast: held alive but allocated before free_before, so it is excluded from every
    # delta yet shrinks the free heap during the load (the allocation-context test).
    ballast = bytearray(BALLAST_BYTES) if BALLAST_BYTES > 0 else b""
    gc.collect()
    free_before = gc.mem_free()

    effect_registry = PackRegistry(item_attr="BUILD")
    effect_registry.scan_dir("packs/effects", "packs.effects")
    rule_registry = PackRegistry(item_attr="RULE")
    rule_registry.scan_dir("packs/rules", "packs.rules")
    scene_registry = SceneRegistry()
    scene_registry.scan_dir("packs/scenes", "packs.scenes")
    gc.collect()
    free_after_registries = gc.mem_free()

    effect_manager = EffectManager(registry=effect_registry, outputs=[NullEffectOutput()])
    timer = Timer()
    engine = GameEngine(effect_controls=effect_manager, timer=timer)
    manager = SceneManager(engine, effect_registry, rule_registry, scene_registry)
    gc.collect()
    free_after_manager = gc.mem_free()

    manager.load(SCENE_NAME)
    gc.collect()
    free_after_load = gc.mem_free()

    manager.update()  # applies the load transition; scene is now active
    gc.collect()
    free_after_update = gc.mem_free()

    # Finer breakdown so the headless-vs-in-situ gap can be localized: is the excess in
    # `load` (scene-graph instantiation) or `update` (first tick), and at what free-heap
    # level. `free_at_load` is the free heap when manager.load runs (shrunk by ballast).
    print(
        "__SCENE_STAGES "
        f"ballast={len(ballast)}, free_at_start={free_before}, "
        f"registries={free_before - free_after_registries}, "
        f"manager={free_after_registries - free_after_manager}, "
        f"free_at_load={free_after_manager}, "
        f"load={free_after_manager - free_after_load}, "
        f"update={free_after_load - free_after_update}, "
        f"free_after={free_after_update}"
    )
    registry_bytes = free_before - free_after_registries
    scene_bytes = free_after_registries - free_after_update
    return manager, effect_manager, timer, registry_bytes, scene_bytes


def run_engine_host() -> None:
    """Run the bare-loop baseline with a rule-less GameEngine driving an EffectManager."""
    effect_manager, game_engine, game_state, heap_bytes = _build_engine_host()
    timer = Timer()
    perf = PerformanceTracker(log_interval=LOG_INTERVAL_SECONDS)

    print_profile_header(
        component="baseline.engine_host",
        sweep_axes=[],
        sweep_values=[],
        target_fps=TARGET_FPS,
    )

    while True:
        perf.start_frame()

        perf.start_update_time()
        timer.update()
        effect_manager.update(timer)
        game_engine.update(game_state)
        perf.add_update_time()

        if perf.complete_frame():
            busy_time = perf.update_time_total + perf.render_time_total
            cpu_percent = 100.0 * busy_time / (perf.last_frame_end - perf.start_time)
            print_stats_line(perf, cpu_percent=f"{cpu_percent:.2f}%")
            # Per-MCU baselines row -- read once cpu_percent has converged.
            print_table_row(
                "per_mcu_baselines",
                ["engine-host", f"{cpu_percent:.2f}%", heap_bytes],
            )


def run_satellite() -> None:
    """Run the bare-loop baseline with an EffectManager and command-receive scaffold."""
    effect_manager, heap_bytes = _build_satellite()
    timer = Timer()
    perf = PerformanceTracker(log_interval=LOG_INTERVAL_SECONDS)

    print_profile_header(
        component="baseline.satellite",
        sweep_axes=[],
        sweep_values=[],
        target_fps=TARGET_FPS,
    )

    while True:
        perf.start_frame()

        perf.start_update_time()
        timer.update()
        effect_manager.update(timer)
        perf.add_update_time()

        if perf.complete_frame():
            busy_time = perf.update_time_total + perf.render_time_total
            cpu_percent = 100.0 * busy_time / (perf.last_frame_end - perf.start_time)
            print_stats_line(perf, cpu_percent=f"{cpu_percent:.2f}%")
            # Per-MCU baselines row -- read once cpu_percent has converged.
            print_table_row(
                "per_mcu_baselines",
                ["satellite", f"{cpu_percent:.2f}%", heap_bytes],
            )


def run_scene_content() -> None:
    """Load SCENE_NAME headless and report its registry + scene-graph heap (#448)."""
    manager, effect_manager, timer, registry_bytes, scene_bytes = _build_scene_content()
    perf = PerformanceTracker(log_interval=LOG_INTERVAL_SECONDS)

    print_profile_header(
        component=f"baseline.scene_content.{SCENE_NAME}",
        sweep_axes=[],
        sweep_values=[],
        target_fps=TARGET_FPS,
    )
    # Per-scene content footprint: registry-scan heap and scene-load heap, headless
    # (no hardware), so the scene graph is separated from the matrix pixel buffers.
    print_table_row(
        "scene_content_memory",
        [SCENE_NAME, registry_bytes, scene_bytes],
    )

    while True:
        perf.start_frame()

        perf.start_update_time()
        timer.update()
        manager.update()
        effect_manager.update(timer)
        perf.add_update_time()

        if perf.complete_frame():
            busy_time = perf.update_time_total + perf.render_time_total
            cpu_percent = 100.0 * busy_time / (perf.last_frame_end - perf.start_time)
            print_stats_line(perf, cpu_percent=f"{cpu_percent:.2f}%")


if MODE == "engine_host":
    run_engine_host()
elif MODE == "satellite":
    run_satellite()
elif MODE == "scene_content":
    run_scene_content()
else:
    raise ValueError(f"Unknown MODE: {MODE!r}")

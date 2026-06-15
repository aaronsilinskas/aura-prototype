"""CircuitPython baseline profiler — measures each board's fixed framework tax.

Runs the framework loop with zero rules, zero registered effect packs, and
zero components, so the reported FPS/CPU/heap numbers represent the cost of
the engine itself before any component-specific work is added. Every other
profiler under ``examples/hardware/profiling/`` should be compared against
this baseline.

Two modes are available — set ``MODE`` below:

- ``"engine_host"`` — the framework loop driving ``GameEngine.update`` with an
  ``EffectManager`` that has no registered outputs and no rules. Models a
  device that owns game logic but renders nothing itself (e.g. a controller).
- ``"satellite"`` — the framework loop driving an ``EffectManager`` with a
  no-op ``EffectOutput`` (command-receive scaffold, no pixels, no rules, no
  components). Models a device that only receives effect commands and would
  normally drive hardware outputs.

Both modes print the shared profiling header once at startup and the uniform
stats line every ``LOG_INTERVAL_SECONDS``.

Hardware
--------
- Any CircuitPython-compatible board. No additional wiring is required — this
  profiler does not drive any LEDs or other peripherals.

Installation
------------
1. Install CircuitPython on your board:
   https://learn.adafruit.com/welcome-to-circuitpython/installing-circuitpython

2. Copy the effects/ and engine/ directories from this repo onto the CIRCUITPY
   drive so they live at /CIRCUITPY/effects/ and /CIRCUITPY/engine/.

3. Copy this file's sibling module to the root of the CIRCUITPY drive so it is
   importable as a top-level module:
     cp examples/hardware/profiling/profiling_helpers.py /Volumes/CIRCUITPY/profiling_helpers.py

4. Copy this file to the root of the CIRCUITPY drive as code.py:
     cp examples/hardware/profiling/baseline_profiler.py /Volumes/CIRCUITPY/code.py

5. The board will reboot and start running automatically.

Configuration
-------------
- MODE: "engine_host" or "satellite"
- TARGET_FPS: informational only — included in the header for comparison
  against component profilers with real per-frame work
- LOG_INTERVAL_SECONDS: how often the stats line is printed
"""

from __future__ import annotations

import time

from profiling_helpers import (
    print_profile_header,
    print_stats_line,
    stats_due,
)

from effects.performance import PerformanceTracker
from engine.effects.manager import EffectManager, EffectOutput
from engine.engine import GameEngine
from engine.packs import PackRegistry
from engine.state import GameState, SceneControls
from engine.timer import Timer

try:
    from typing import Final
except ImportError:
    pass

MODE: Final = "engine_host"  # or "satellite"
TARGET_FPS: Final = 60.0
LOG_INTERVAL_SECONDS: Final = 5.0


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


def _build_engine_host() -> tuple[EffectManager, GameEngine, GameState]:
    registry = PackRegistry(item_attr="BUILD")
    effect_manager = EffectManager(registry=registry, outputs=[])
    game_engine = GameEngine(effect_controls=effect_manager)
    game_state = game_engine.create_state(SceneControls())
    return effect_manager, game_engine, game_state


def _build_satellite() -> EffectManager:
    registry = PackRegistry(item_attr="BUILD")
    effect_manager = EffectManager(registry=registry, outputs=[NullEffectOutput()])
    return effect_manager


def run_engine_host() -> None:
    """Run the bare-loop baseline with a rule-less GameEngine driving an EffectManager."""
    effect_manager, game_engine, game_state = _build_engine_host()
    timer = Timer()
    perf = PerformanceTracker(log_interval=LOG_INTERVAL_SECONDS)

    print_profile_header(
        component="baseline.engine_host",
        sweep_axes=[],
        sweep_values=[],
        target_fps=TARGET_FPS,
    )

    while True:
        current_time = time.monotonic()
        perf.start_frame()

        perf.start_update_time()
        timer.update()
        effect_manager.update(timer)
        game_engine.update(game_state)
        perf.add_update_time()

        due = stats_due(perf, current_time)
        perf.complete_frame(current_time)
        if due:
            busy_time = perf.update_time_total + perf.render_time_total
            cpu_percent = 100.0 * busy_time / (current_time - perf.start_time)
            print_stats_line(perf, current_time, cpu_percent=f"{cpu_percent:.2f}%")


def run_satellite() -> None:
    """Run the bare-loop baseline with an EffectManager and command-receive scaffold."""
    effect_manager = _build_satellite()
    timer = Timer()
    perf = PerformanceTracker(log_interval=LOG_INTERVAL_SECONDS)

    print_profile_header(
        component="baseline.satellite",
        sweep_axes=[],
        sweep_values=[],
        target_fps=TARGET_FPS,
    )

    while True:
        current_time = time.monotonic()
        perf.start_frame()

        perf.start_update_time()
        timer.update()
        effect_manager.update(timer)
        perf.add_update_time()

        due = stats_due(perf, current_time)
        perf.complete_frame(current_time)
        if due:
            busy_time = perf.update_time_total + perf.render_time_total
            cpu_percent = 100.0 * busy_time / (current_time - perf.start_time)
            print_stats_line(perf, current_time, cpu_percent=f"{cpu_percent:.2f}%")


if MODE == "engine_host":
    run_engine_host()
elif MODE == "satellite":
    run_satellite()
else:
    raise ValueError(f"Unknown MODE: {MODE!r}")

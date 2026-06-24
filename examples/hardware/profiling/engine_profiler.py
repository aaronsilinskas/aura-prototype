"""CircuitPython engine profiler -- drives the real `GameEngine.update(state)`
dispatch loop with a synthetic rule set and a controlled number of queued events
per tick, to measure the engine cost terms (`tick_fixed_ms`, `per_rule_ms`,
`per_event_ms`) for the `engine_component_costs` table in
`docs/hardware/recorded-metrics.md` (see also
`docs/hardware/calibration-guide.md`).

Sweeps two axes **independently**, each holding the other at a fixed reference
of 1 so the slopes are clean:

- **rule_count** -- `RULE_COUNTS`, with `events_per_tick` held at
  `REFERENCE_EVENTS_PER_TICK` (1). `per_rule_ms` is the slope of Update Time vs
  rule count.
- **events_per_tick** -- `EVENTS_PER_TICK_VALUES`, with `rule_count` held at
  `REFERENCE_RULE_COUNT` (1). `per_event_ms` is the slope of Update Time vs
  events per tick.

The `(rule_count=0, events_per_tick=0)` point is profiled first and is the
`tick_fixed_ms` zero point -- it reproduces the engine-host baseline measured
by `baseline_profiler.py` in `engine_host` mode (a rule-less `GameEngine.update`
loop), so the two overlap -- don't double-count the fixed engine tick on top of
that baseline.

For each `(rule_count, events_per_tick)` point, the profiler:

1. Builds a `GameEngine` with `rule_count` synthetic `_ProfilerRule` instances
   registered, each of which handles exactly one `_ProfilerEvent` via a no-op
   handler registered with `self.on(...)`.
2. Runs a steady-state loop. Each frame, `events_per_tick` `_ProfilerEvent`
   instances are queued via `state.queue_event(...)` (re-queued every frame,
   since `update()` drains the queue each tick), then `game_engine.update(state)`
   is called and timed.
3. Reports `PerformanceTracker` stats via the uniform stats line, including
   both sweep values (`rule_count` and `events_per_tick`) for this point.

After the sweep completes, the profiler fits `per_rule_ms` and `per_event_ms`
from the slopes (via `linear_fit`), reads `tick_fixed_ms` from the `(0, 0)`
point, and prints the completed `engine_component_costs` table row as a
`__TABLE_ROW` line ready to paste into `docs/hardware/recorded-metrics.md`.
`router_overhead_ms` is out of scope here and is emitted as `_TBD_`.

Hardware
--------
- Any CircuitPython-compatible board. No additional wiring is required -- this
  profiler does not drive any LEDs or other peripherals.

Installation
------------
1. Install CircuitPython on your board:
   https://learn.adafruit.com/welcome-to-circuitpython/installing-circuitpython

2. Run the deploy script to copy all source files and set code.py:
     python scripts/deploy.py examples/hardware/profiling/engine_profiler.py
   The board reboots and starts running automatically.

Configuration
-------------
- RULE_COUNTS: rule counts to sweep, with events_per_tick held at
  REFERENCE_EVENTS_PER_TICK. Read the slope of Update Time vs rule count for
  `per_rule_ms`.
- EVENTS_PER_TICK_VALUES: events-per-tick values to sweep, with rule_count
  held at REFERENCE_RULE_COUNT. Read the slope of Update Time vs events per
  tick for `per_event_ms`.
- REFERENCE_RULE_COUNT / REFERENCE_EVENTS_PER_TICK: the fixed reference value
  held on the axis not currently being swept.
- TARGET_FPS: informational only -- included in the header for comparison
  against other profilers.
- DISPLAY_SECONDS: how long to spend on each sweep point before advancing.
- LOG_INTERVAL_SECONDS: how often the stats line is printed.
"""

from __future__ import annotations

import time

from effects.performance import PerformanceTracker
from engine.effects.manager import EffectManager
from engine.engine import GameEngine, GameRule
from engine.events import Event, EventGroup
from engine.packs import PackRegistry
from engine.state import GameState, SceneControls
from hardware.shared.profiling_helpers import (
    linear_fit,
    print_profile_header,
    print_stats_line,
    print_table_row,
)

try:
    from typing import Final
except ImportError:
    pass

RULE_COUNTS: Final = [0, 1, 2, 4, 8]
EVENTS_PER_TICK_VALUES: Final = [0, 1, 2, 4, 8]
REFERENCE_RULE_COUNT: Final = 1
REFERENCE_EVENTS_PER_TICK: Final = 1
TARGET_FPS: Final = 60.0
DISPLAY_SECONDS: Final = 10.0
LOG_INTERVAL_SECONDS: Final = 5.0

_PROFILER_EVENT_GROUP: Final = EventGroup("profiler")


class _ProfilerEvent(Event):
    """Synthetic event type queued each tick to exercise the dispatch loop."""

    __slots__ = []

    def __init__(self) -> None:
        super().__init__(_PROFILER_EVENT_GROUP, "tick")


class _ProfilerRule(GameRule):
    """Synthetic rule registering one no-op handler for `_ProfilerEvent`."""

    def __init__(self) -> None:
        self.on(_ProfilerEvent, self._handle_tick)

    def _handle_tick(self, event: _ProfilerEvent, state: GameState) -> None:
        """No-op handler -- exists only to be dispatched to by the engine."""


def _build_engine(rule_count: int) -> tuple[GameEngine, GameState]:
    registry = PackRegistry(item_attr="BUILD")
    effect_manager = EffectManager(registry=registry, outputs=[])
    game_engine = GameEngine(effect_controls=effect_manager)
    game_engine.set_rules([_ProfilerRule() for _ in range(rule_count)])
    game_state = game_engine.create_state(SceneControls())
    return game_engine, game_state


def _run_point(rule_count: int, events_per_tick: int) -> float:
    """Run one steady-state sweep point and return its average Update Time (ms).

    Reports the uniform stats line each interval while the point runs, then
    returns the steady-state per-tick Update Time so the caller can fit the
    `tick_fixed_ms` / `per_rule_ms` / `per_event_ms` constants across the sweep.
    """
    game_engine, game_state = _build_engine(rule_count)
    perf = PerformanceTracker(log_interval=LOG_INTERVAL_SECONDS)

    # Pre-allocate the events queued each frame -- update() drains the queue
    # by popping, so the same instances are re-queued every tick without
    # allocating in the hot loop below.
    events = [_ProfilerEvent() for _ in range(events_per_tick)]

    print_profile_header(
        component="engine",
        sweep_axes=["rule_count", "events_per_tick"],
        sweep_values=[rule_count, events_per_tick],
        target_fps=TARGET_FPS,
    )

    next_change_time = time.monotonic() + DISPLAY_SECONDS
    while True:
        perf.start_frame()
        perf.start_update_time()
        for i in range(events_per_tick):
            game_state.queue_event(events[i])
        game_engine.update(game_state)
        perf.add_update_time()

        if perf.complete_frame():
            print_stats_line(
                perf,
                rule_count=rule_count,
                events_per_tick=events_per_tick,
            )

        if perf.last_frame_end > next_change_time:
            break

    return perf.update_time_total / perf.frame_count * 1000.0


def run() -> None:
    """Sweep rule_count and events_per_tick independently, each at a fixed reference."""
    # (0, 0) point: tick_fixed_ms zero point, reproduces the engine-host baseline.
    tick_fixed_ms = _run_point(rule_count=0, events_per_tick=0)

    # Sweep rule_count, holding events_per_tick at the reference -> per_rule_ms slope.
    rule_counts = []
    rule_update_ms = []
    for rule_count in RULE_COUNTS:
        if rule_count == 0:
            continue  # already covered by the (0, 0) point above
        rule_counts.append(rule_count)
        rule_update_ms.append(_run_point(rule_count, REFERENCE_EVENTS_PER_TICK))

    # Sweep events_per_tick, holding rule_count at the reference -> per_event_ms slope.
    event_counts = []
    event_update_ms = []
    for events_per_tick in EVENTS_PER_TICK_VALUES:
        if events_per_tick == 0:
            continue  # already covered by the (0, 0) point above
        event_counts.append(events_per_tick)
        event_update_ms.append(_run_point(REFERENCE_RULE_COUNT, events_per_tick))

    per_rule_ms, _ = linear_fit(rule_counts, rule_update_ms)
    per_event_ms, _ = linear_fit(event_counts, event_update_ms)

    # router_overhead_ms is command-shipping cost to remote MCUs, charged to the
    # engine host -- it has no seam in the GameEngine.update tick loop measured
    # here, so it stays _TBD_ (see docs/hardware/recorded-metrics.md).
    print_table_row(
        "engine_component_costs",
        [
            f"{tick_fixed_ms:.4f}",
            f"{per_rule_ms:.4f}",
            f"{per_event_ms:.4f}",
            "_TBD_",
        ],
    )


run()

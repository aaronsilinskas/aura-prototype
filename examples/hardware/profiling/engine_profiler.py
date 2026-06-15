"""CircuitPython engine profiler -- drives the real `GameEngine.update(state)`
dispatch loop with a synthetic rule set and a controlled number of queued events
per tick, to extract the `EngineComponent` cost terms the capacity estimator
already models (`tick_fixed_ms`, `per_rule_ms`, `per_event_ms`; see
`docs/hardware/capacity-model.md` and #409).

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
loop), so the estimator must not double-count the fixed engine tick on top of
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
from hardware.shared.profiling_helpers import print_profile_header, print_stats_line, stats_due

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


def _run_point(rule_count: int, events_per_tick: int) -> None:
    """Run one steady-state sweep point and report its stats line."""
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
        current_time = time.monotonic()

        perf.start_frame()
        perf.start_update_time()
        for i in range(events_per_tick):
            game_state.queue_event(events[i])
        game_engine.update(game_state)
        perf.add_update_time()

        due = stats_due(perf, current_time)
        perf.complete_frame(current_time)
        if due:
            print_stats_line(
                perf,
                current_time,
                rule_count=rule_count,
                events_per_tick=events_per_tick,
            )

        if current_time > next_change_time:
            break


def run() -> None:
    """Sweep rule_count and events_per_tick independently, each at a fixed reference."""
    # (0, 0) point: tick_fixed_ms zero point, reproduces the engine-host baseline.
    _run_point(rule_count=0, events_per_tick=0)

    # Sweep rule_count, holding events_per_tick at the reference -> per_rule_ms slope.
    for rule_count in RULE_COUNTS:
        if rule_count == 0:
            continue  # already covered by the (0, 0) point above
        _run_point(rule_count=rule_count, events_per_tick=REFERENCE_EVENTS_PER_TICK)

    # Sweep events_per_tick, holding rule_count at the reference -> per_event_ms slope.
    for events_per_tick in EVENTS_PER_TICK_VALUES:
        if events_per_tick == 0:
            continue  # already covered by the (0, 0) point above
        _run_point(rule_count=REFERENCE_RULE_COUNT, events_per_tick=events_per_tick)


run()

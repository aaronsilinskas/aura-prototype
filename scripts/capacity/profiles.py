"""Data shapes for the capacity estimator.

`scripts/` is CPython-only tooling and is exempt from the CircuitPython/MicroPython
constraints described in `docs/agents/domain.md` (dataclasses are fine here).

Board profiles describe a microcontroller's available budget (CPU and heap) and a
per-MCU baseline cost for the two roles a board can play in a prop:

- **engine-host**: runs the `GameEngine` tick loop, owns rules and the event queue.
  Exactly one per prop.
- **satellite**: a thin command executor with no rules, driven by the engine-host
  over the network.

Prop profiles describe the workload to be placed: a list of components, each with a
cost model that can be evaluated against a board's `frame_budget_ms` to produce a
CPU reservation percentage.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class McuBaseline:
    """Fixed CPU and heap cost an MCU role consumes before any components are packed.

    `cpu_percent` is a percentage of the MCU's per-frame CPU budget (0-100).
    `heap_bytes` is deducted from the board's total free heap.
    """

    cpu_percent: float
    heap_bytes: int


@dataclass(frozen=True)
class BoardProfile:
    """Capacity profile for one board model running a given runtime.

    `frame_budget_ms` is derived from `target_fps` (e.g. 24 FPS -> ~41.67ms) and is
    the per-frame time budget that component costs (in ms) are reserved against.

    `headroom_reserve_percent` is the default fraction of CPU budget held back across
    all MCUs of this board, tunable per assignment via `assign(..., headroom_reserve_percent=...)`.
    """

    name: str
    runtime: str
    target_fps: float
    peripherals: tuple[str, ...]
    total_free_heap_bytes: int
    engine_host_baseline: McuBaseline
    satellite_baseline: McuBaseline
    headroom_reserve_percent: float = 20.0

    @property
    def frame_budget_ms(self) -> float:
        """Per-frame time budget in milliseconds, derived from `target_fps`."""
        return 1000.0 / self.target_fps


@dataclass(frozen=True)
class EngineComponent:
    """The engine-host component: the `GameEngine` tick loop plus rules and router.

    Cost model (in ms, evaluated once per frame):

        cost_ms = tick_fixed_ms
                + per_rule_ms * rules
                + per_event_ms * events_per_tick
                + router_overhead_ms * remote_mcus

    `router_overhead_ms` is a per-remote-MCU command/event overhead charged to the
    engine's MCU (not a pixel-bandwidth cost) -- it scales with how many other MCUs
    the engine must send commands/events to, not with strip length.
    """

    name: str
    tick_fixed_ms: float
    per_rule_ms: float
    per_event_ms: float
    router_overhead_ms: float
    rules: int
    events_per_tick: int
    remote_mcus: int

    @property
    def cost_ms(self) -> float:
        """Estimated per-frame CPU cost in milliseconds."""
        return (
            self.tick_fixed_ms
            + self.per_rule_ms * self.rules
            + self.per_event_ms * self.events_per_tick
            + self.router_overhead_ms * self.remote_mcus
        )


@dataclass(frozen=True)
class SimpleComponent:
    """A component with a fixed, pre-computed per-frame cost in milliseconds.

    Used for non-engine workloads (e.g. effect renderers, input pollers) where the
    cost model is a single constant rather than a formula.
    """

    name: str
    cost_ms: float


@dataclass(frozen=True)
class PropProfile:
    """Workload description for one prop: the components that must be placed on MCUs.

    Exactly one component in `components` must be an `EngineComponent` -- it anchors
    the engine-host MCU. All other components are placeable on any MCU (engine-host
    or satellite).
    """

    name: str
    components: list["EngineComponent | SimpleComponent"] = field(default_factory=list)

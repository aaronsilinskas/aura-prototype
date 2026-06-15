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
class BusBudget:
    """Bandwidth budget for one shared bus (I2C/SPI/I2S) on a board.

    `bandwidth_bytes_per_sec` is the total bytes/sec the bus can sustain across all
    components that share it. Components declare their own usage as
    `transaction_size * frequency` (see `PixelScopeComponent.i2c_bandwidth_bytes_per_sec`).
    """

    bandwidth_bytes_per_sec: float


@dataclass(frozen=True)
class BoardProfile:
    """Capacity profile for one board model running a given runtime.

    `frame_budget_ms` is derived from `target_fps` (e.g. 24 FPS -> ~41.67ms) and is
    the per-frame time budget that component costs (in ms) are reserved against.

    `headroom_reserve_percent` is the default fraction of CPU budget held back across
    all MCUs of this board, tunable per assignment via `assign(..., headroom_reserve_percent=...)`.

    `gc_margin_bytes` is a fixed amount of heap held back on every MCU of this board,
    on top of the role's `heap_bytes` baseline, to leave room for CircuitPython's
    mark-sweep collector. It should be generous: GC needs free space to work in, and
    fragmentation shrinks the heap that is actually usable for allocations.
    """

    name: str
    runtime: str
    target_fps: float
    peripherals: tuple[str, ...]
    total_free_heap_bytes: int
    engine_host_baseline: McuBaseline
    satellite_baseline: McuBaseline
    headroom_reserve_percent: float = 20.0
    gc_margin_bytes: int = 0
    bus_budgets: dict[str, BusBudget] = field(default_factory=dict)

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

    `memory_footprint_bytes` is the component's static steady-state heap usage
    (profiler-measured via `mem_free` delta; placeholder/synthetic until calibrated).
    """

    name: str
    tick_fixed_ms: float
    per_rule_ms: float
    per_event_ms: float
    router_overhead_ms: float
    rules: int
    events_per_tick: int
    remote_mcus: int
    memory_footprint_bytes: int = 0

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

    `memory_footprint_bytes` is the component's static steady-state heap usage
    (profiler-measured via `mem_free` delta; placeholder/synthetic until calibrated).
    """

    name: str
    cost_ms: float
    memory_footprint_bytes: int = 0


@dataclass(frozen=True)
class ReceiverComponent:
    """A hard-real-time receiver component whose buffer depth trades RAM for deadline relief.

    Cost model is a fixed `cost_ms` (the `fixed_drain` per-tick polling cost) like
    `SimpleComponent`. Its memory footprint grows with `buffer_depth` (e.g. a deeper
    IR pulse buffer or radio FIFO), so raising the buffer depth to relieve a polling
    deadline visibly increases the component's heap usage.

    `memory_footprint_bytes = base_footprint_bytes + bytes_per_buffer_slot * buffer_depth`

    **Deadline constraint**: `max_frame_ms` is a *derived* ceiling, not declared --
    it is how long the receiver's buffer can absorb incoming data before a slow frame
    causes an overflow (dropped data):

        max_frame_ms = buffer_depth / incoming_rate_hz * 1000

    `worst_case_frame_ms` is the worst-case single frame time measured on the
    receiver's MCU (profiler-measured via `PerformanceTracker.frame_time_peak`,
    converted to milliseconds). If `worst_case_frame_ms > max_frame_ms`, the
    co-location is rejected with `conflict_type="deadline"` -- even if CPU
    reservation would otherwise fit. Raising `buffer_depth` raises `max_frame_ms`
    (relieving the deadline) at the cost of a larger `memory_footprint_bytes`.
    """

    name: str
    cost_ms: float
    base_footprint_bytes: int
    bytes_per_buffer_slot: int
    buffer_depth: int
    incoming_rate_hz: float = 0.0
    worst_case_frame_ms: float = 0.0

    @property
    def memory_footprint_bytes(self) -> int:
        """Static steady-state heap usage, including the buffer's current depth."""
        return self.base_footprint_bytes + self.bytes_per_buffer_slot * self.buffer_depth

    @property
    def max_frame_ms(self) -> float | None:
        """Derived hard-real-time deadline: how long the buffer can absorb a slow frame.

        Returns `None` when `incoming_rate_hz` is 0 (no deadline declared -- e.g. a
        receiver not yet profiled for incoming rate).
        """
        if self.incoming_rate_hz <= 0:
            return None
        return self.buffer_depth / self.incoming_rate_hz * 1000.0


@dataclass(frozen=True)
class PixelScopeComponent:
    """One pixel scope's workload: a per-scope splittable LED render+flush cost.

    Unlike `SimpleComponent` / `ReceiverComponent` / `EngineComponent` (which are
    indivisible and always packed as a single unit), each `PixelScopeComponent` in a
    prop's `components` list may be placed on its own MCU -- the packer can spread a
    prop's pixel scopes across multiple satellites independently.

    Cost model (in ms, evaluated once per frame):

        cost_ms = stack_depth * worst_case_effect_per_pixel_ms * pixel_count + flush_ms

    `stack_depth` is the maximum number of concurrent `add_effect` layers expected on
    this scope (a scene-declared workload parameter); it defaults to 1.

    `driver` is one of `"neopixel_pwm"` or `"is31fl3741_matrix"` -- the driver
    dimension changes `worst_case_effect_per_pixel_ms`, `flush_ms`, and I2C bus usage.
    NeoPixel PWM is off the I2C bus, so `i2c_transaction_bytes` and
    `i2c_frequency_hz` should be left at 0 for that driver.

    `memory_footprint_bytes` is the component's static steady-state heap usage
    (profiler-measured via `mem_free` delta; placeholder/synthetic until calibrated).
    """

    name: str
    driver: str
    pixel_count: int
    worst_case_effect_per_pixel_ms: float
    flush_ms: float
    stack_depth: int = 1
    i2c_transaction_bytes: int = 0
    i2c_frequency_hz: float = 0
    memory_footprint_bytes: int = 0

    @property
    def cost_ms(self) -> float:
        """Estimated per-frame CPU cost in milliseconds."""
        return self.stack_depth * self.worst_case_effect_per_pixel_ms * self.pixel_count + (
            self.flush_ms
        )

    @property
    def i2c_bandwidth_bytes_per_sec(self) -> float:
        """I2C bus bandwidth this scope's flush consumes, in bytes/sec.

        Zero for drivers that are off the I2C bus (e.g. NeoPixel PWM).
        """
        return self.i2c_transaction_bytes * self.i2c_frequency_hz


@dataclass(frozen=True)
class PropProfile:
    """Workload description for one prop: the components that must be placed on MCUs.

    Exactly one component in `components` must be an `EngineComponent` -- it anchors
    the engine-host MCU. All other components are placeable on any MCU (engine-host
    or satellite).
    """

    name: str
    components: list[
        "EngineComponent | SimpleComponent | ReceiverComponent | PixelScopeComponent"
    ] = field(default_factory=list)

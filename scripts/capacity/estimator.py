"""CPU and memory bin-packing assignment of a prop's components onto a board's MCUs.

See `docs/hardware/capacity-model.md` for the formulas this module implements.
"""

from dataclasses import dataclass

from scripts.capacity.profiles import (
    BoardProfile,
    EngineComponent,
    IrTransmitComponent,
    PixelScopeComponent,
    PropProfile,
    ReceiverComponent,
    SimpleComponent,
    SoundComponent,
    VibrationComponent,
)


def _ir_tx_blocking_send_ms(prop: PropProfile) -> float:
    """Return the prop's `IrTransmitComponent.blocking_send_ms`, or 0.0 if none.

    `PulseOut.send` blocks for the whole pulse train -- this soft cost is added to
    every `ReceiverComponent`'s worst-case frame time when checking the hard-real-time
    deadline (#398), since a co-located receiver's buffer must absorb the gap while
    the transmitter blocks.
    """
    for component in prop.components:
        if isinstance(component, IrTransmitComponent):
            return component.blocking_send_ms
    return 0.0


def _deadline_conflict(prop: PropProfile) -> "ReceiverComponent | None":
    """Return the first receiver whose worst-case frame blows its derived deadline.

    `max_frame_ms` is `None` when a receiver has no declared `incoming_rate_hz` --
    such receivers have no deadline to check.

    The worst-case frame time used for this check adds the prop's IR-transmit
    component's `blocking_send_ms` (if any) -- `PulseOut.send` blocks for the whole
    pulse train, so a co-located transmit contributes to the receiver's worst-case
    frame even though it is a soft cost not reflected in `cost_ms`.
    """
    ir_tx_blocking_ms = _ir_tx_blocking_send_ms(prop)
    for component in prop.components:
        if not isinstance(component, ReceiverComponent):
            continue
        max_frame_ms = component.max_frame_ms
        if max_frame_ms is None:
            continue
        worst_case_frame_ms = component.worst_case_frame_ms + ir_tx_blocking_ms
        if worst_case_frame_ms > max_frame_ms:
            return component
    return None


def _peripheral_conflict(prop: PropProfile, board: BoardProfile) -> tuple[str, int, int] | None:
    """Return `(peripheral, required, available)` for the first over-budget peripheral.

    Sums each component's `peripherals_required` (e.g. `{"i2s": 1}`) across the
    prop's components and compares the total against `board.peripheral_budgets`.
    Peripherals with no declared budget are treated as unconstrained. Returns `None`
    if every required peripheral is within its budget.
    """
    usage: dict[str, int] = {}
    for component in prop.components:
        for peripheral, count in getattr(component, "peripherals_required", {}).items():
            usage[peripheral] = usage.get(peripheral, 0) + count

    for peripheral, required in usage.items():
        budget = board.peripheral_budgets.get(peripheral)
        if budget is not None and required > budget.count:
            return peripheral, required, budget.count
    return None


@dataclass(frozen=True)
class ComponentAssignment:
    """One component placed on an MCU, with its CPU reservation."""

    name: str
    reserved_percent: float


@dataclass(frozen=True)
class McuAssignment:
    """One MCU in an assignment result, with the components packed onto it."""

    role: str
    components: list[ComponentAssignment]
    remaining_headroom_percent: float
    remaining_heap_bytes: float


@dataclass(frozen=True)
class AssignmentResult:
    """Outcome of `assign`: either a feasible placement or an infeasible/conflict reason."""

    feasible: bool
    mcus: list[McuAssignment]
    co_location_validated: bool
    reason: str | None = None
    conflict_type: str | None = None


def _reserved_percent(cost_ms: float, frame_budget_ms: float) -> float:
    """Convert a component's cost in milliseconds to a percentage of the frame budget."""
    return cost_ms / frame_budget_ms * 100.0


def _usable_percent(board: BoardProfile, role: str, reserve: float) -> float:
    """Return the CPU percentage available for component reservations on a role's MCU."""
    baseline = board.engine_host_baseline if role == "engine-host" else board.satellite_baseline
    return 100.0 - baseline.cpu_percent - reserve


def _usable_heap(board: BoardProfile, role: str) -> float:
    """Return the heap (in bytes) available for component footprints on a role's MCU.

    `usable_heap = total_free_heap_bytes - baseline.heap_bytes - gc_margin_bytes`
    """
    baseline = board.engine_host_baseline if role == "engine-host" else board.satellite_baseline
    return board.total_free_heap_bytes - baseline.heap_bytes - board.gc_margin_bytes


def _memory_footprint_bytes(
    component: (
        "EngineComponent | SimpleComponent | ReceiverComponent | PixelScopeComponent"
        " | SoundComponent | VibrationComponent | IrTransmitComponent"
    ),
) -> int:
    """Return a component's static steady-state heap footprint in bytes."""
    return component.memory_footprint_bytes


def assign(
    prop: PropProfile,
    board: BoardProfile,
    headroom_reserve_percent: float | None = None,
) -> AssignmentResult:
    """Assign a prop's components onto the fewest MCUs of `board`.

    Packs components onto MCUs keeping summed CPU reservation per MCU at or below
    `100% - role_baseline_cpu_percent - headroom_reserve_percent`. Exactly one MCU
    (the one hosting the `EngineComponent`) is the engine-host; all others are
    satellites.

    Components are packed greedily, largest reservation first (first-fit-decreasing),
    starting a new satellite MCU whenever a component does not fit on any existing MCU.

    `headroom_reserve_percent` overrides `board.headroom_reserve_percent` if given.

    Returns an infeasible `AssignmentResult` naming the violated constraint if even
    the largest single component cannot fit on a fresh satellite MCU
    (`conflict_type="cpu"`).

    After CPU packing succeeds, each MCU's summed `memory_footprint_bytes` is checked
    against `total_free_heap_bytes - role_baseline_heap_bytes - gc_margin_bytes`. If any
    MCU overflows, returns an infeasible `AssignmentResult` with `conflict_type="memory"`.
    """
    # Hard-real-time deadline constraint: a receiver whose worst-case frame exceeds
    # its derived `max_frame_ms` is rejected outright -- the deadline dominates the
    # budget, even when CPU reservation would otherwise fit (checked before packing).
    deadline_violator = _deadline_conflict(prop)
    if deadline_violator is not None:
        return AssignmentResult(
            feasible=False,
            mcus=[],
            co_location_validated=False,
            reason=(
                f"component '{deadline_violator.name}' worst-case frame "
                f"{deadline_violator.worst_case_frame_ms:.2f}ms exceeds its derived "
                f"deadline max_frame_ms={deadline_violator.max_frame_ms:.2f}ms "
                f"(buffer_depth={deadline_violator.buffer_depth} / "
                f"incoming_rate_hz={deadline_violator.incoming_rate_hz:.2f} * 1000)"
            ),
            conflict_type="deadline",
        )

    # Peripheral-count constraint: finite I2S/SPI/I2C/PWM units per board. Checked
    # before CPU/memory packing, alongside the deadline constraint -- a peripheral
    # conflict (e.g. two components both requiring the single I2S) is a structural
    # impossibility independent of CPU headroom.
    peripheral_violation = _peripheral_conflict(prop, board)
    if peripheral_violation is not None:
        peripheral, required, available = peripheral_violation
        return AssignmentResult(
            feasible=False,
            mcus=[],
            co_location_validated=False,
            reason=(
                f"prop requires {required} '{peripheral}' peripheral(s) but board "
                f"'{board.name}' provides {available}"
            ),
            conflict_type="peripheral",
        )

    reserve = (
        board.headroom_reserve_percent
        if headroom_reserve_percent is None
        else headroom_reserve_percent
    )

    frame_budget_ms = board.frame_budget_ms
    reservations = [
        (component.name, _reserved_percent(component.cost_ms, frame_budget_ms))
        for component in prop.components
    ]
    footprints = {
        component.name: _memory_footprint_bytes(component) for component in prop.components
    }

    engine_usable = _usable_percent(board, "engine-host", reserve)
    satellite_usable = _usable_percent(board, "satellite", reserve)
    engine_usable_heap = _usable_heap(board, "engine-host")
    satellite_usable_heap = _usable_heap(board, "satellite")

    # The engine-host MCU is seeded with the engine component (exactly one per prop)
    # and packed first; remaining components are packed first-fit-decreasing.
    engine_name = next((c.name for c in prop.components if isinstance(c, EngineComponent)), None)
    remaining = sorted(
        (item for item in reservations if item[0] != engine_name),
        key=lambda item: item[1],
        reverse=True,
    )

    bins: list[dict] = []
    if engine_name is not None:
        engine_percent = next(p for n, p in reservations if n == engine_name)
        if engine_percent > engine_usable:
            return AssignmentResult(
                feasible=False,
                mcus=[],
                co_location_validated=False,
                reason=(
                    f"engine component reserves {engine_percent:.2f}% which exceeds the "
                    f"engine-host's usable budget {engine_usable:.2f}% (100% - baseline "
                    f"{board.engine_host_baseline.cpu_percent:.2f}% - headroom reserve "
                    f"{reserve:.2f}%)"
                ),
                conflict_type="cpu",
            )
        bins.append(
            {
                "role": "engine-host",
                "usable": engine_usable,
                "used": engine_percent,
                "usable_heap": engine_usable_heap,
                "items": [(engine_name, engine_percent)],
            }
        )

    for name, percent in remaining:
        placed = False
        for bin_ in bins:
            if bin_["used"] + percent <= bin_["usable"]:
                bin_["used"] += percent
                bin_["items"].append((name, percent))
                placed = True
                break
        if not placed:
            if percent > satellite_usable:
                return AssignmentResult(
                    feasible=False,
                    mcus=[],
                    co_location_validated=False,
                    reason=(
                        f"component '{name}' reserves {percent:.2f}% which exceeds a "
                        f"satellite's usable budget {satellite_usable:.2f}% (100% - baseline "
                        f"{board.satellite_baseline.cpu_percent:.2f}% - headroom reserve "
                        f"{reserve:.2f}%)"
                    ),
                    conflict_type="cpu",
                )
            bins.append(
                {
                    "role": "satellite",
                    "usable": satellite_usable,
                    "used": percent,
                    "usable_heap": satellite_usable_heap,
                    "items": [(name, percent)],
                }
            )

    if not bins:
        bins.append(
            {
                "role": "satellite",
                "usable": satellite_usable,
                "used": 0.0,
                "usable_heap": satellite_usable_heap,
                "items": [],
            }
        )

    for bin_ in bins:
        bin_["used_heap"] = sum(footprints[name] for name, _ in bin_["items"])

    for bin_ in bins:
        if bin_["used_heap"] > bin_["usable_heap"]:
            role_label = "engine-host" if bin_["role"] == "engine-host" else "satellite"
            baseline = (
                board.engine_host_baseline
                if bin_["role"] == "engine-host"
                else board.satellite_baseline
            )
            return AssignmentResult(
                feasible=False,
                mcus=[],
                co_location_validated=False,
                reason=(
                    f"{role_label} MCU's summed memory footprint {bin_['used_heap']} bytes "
                    f"exceeds its usable heap {bin_['usable_heap']:.0f} bytes "
                    f"(total free heap {board.total_free_heap_bytes} - baseline heap "
                    f"{baseline.heap_bytes} - gc margin {board.gc_margin_bytes})"
                ),
                conflict_type="memory",
            )

    # Bus-bandwidth constraint: each shared bus (I2C/SPI/I2S) has a board-wide
    # bandwidth budget. Pixel scopes using an I2C-bus driver (e.g. the IS31FL3741
    # matrix), the vibration component (DRV2605L event rate), and any I2C-polled
    # SimpleComponent (e.g. a LIS3DH per-frame accelerometer read) contribute
    # `transaction_size * frequency` to that bus's total usage,
    # regardless of which MCU they are placed on. NeoPixel PWM scopes contribute 0.
    bus_usage: dict[str, float] = {}
    for component in prop.components:
        if (
            isinstance(component, (PixelScopeComponent, VibrationComponent, SimpleComponent))
            and component.i2c_bandwidth_bytes_per_sec
        ):
            bus_usage["i2c"] = bus_usage.get("i2c", 0.0) + component.i2c_bandwidth_bytes_per_sec

    for bus_name, used in bus_usage.items():
        budget = board.bus_budgets.get(bus_name)
        if budget is not None and used > budget.bandwidth_bytes_per_sec:
            return AssignmentResult(
                feasible=False,
                mcus=[],
                co_location_validated=False,
                reason=(
                    f"{bus_name} bus usage {used:.0f} bytes/sec exceeds its budget "
                    f"{budget.bandwidth_bytes_per_sec:.0f} bytes/sec"
                ),
                conflict_type="bus",
            )

    mcus = [
        McuAssignment(
            role=bin_["role"],
            components=[
                ComponentAssignment(name=name, reserved_percent=percent)
                for name, percent in bin_["items"]
            ],
            remaining_headroom_percent=bin_["usable"] - bin_["used"],
            remaining_heap_bytes=bin_["usable_heap"] - bin_["used_heap"],
        )
        for bin_ in bins
    ]

    return AssignmentResult(
        feasible=True,
        mcus=mcus,
        co_location_validated=True,
    )


def fan_out_mcu_count(result: AssignmentResult, output_component_names: set[str]) -> int:
    """Return the number of MCUs hosting any of `output_component_names`.

    An effect command's router cost scales with how many distinct MCUs the
    engine-host must send that command to -- one per MCU hosting an output in the
    scope, regardless of how many outputs that MCU hosts. Use this count as the
    `remote_mcus` term in `EngineComponent.router_overhead_ms * remote_mcus` for a
    scope's effect commands (excluding the engine-host itself, which never needs a
    network hop).
    """
    return sum(
        1
        for mcu in result.mcus
        if mcu.role != "engine-host"
        and any(c.name in output_component_names for c in mcu.components)
    )

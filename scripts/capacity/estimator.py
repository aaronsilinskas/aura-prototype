"""CPU and memory bin-packing assignment of a prop's components onto a board's MCUs.

See `docs/hardware/capacity-model.md` for the formulas this module implements.
"""

from dataclasses import dataclass

from scripts.capacity.profiles import BoardProfile, EngineComponent, PropProfile


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


def _memory_footprint_bytes(component) -> int:
    """Return a component's static steady-state heap footprint in bytes."""
    return getattr(component, "memory_footprint_bytes", 0)


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

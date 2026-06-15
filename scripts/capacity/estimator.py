"""CPU-only bin-packing assignment of a prop's components onto a board's MCUs.

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


@dataclass(frozen=True)
class AssignmentResult:
    """Outcome of `assign`: either a feasible placement or an infeasible/conflict reason."""

    feasible: bool
    mcus: list[McuAssignment]
    co_location_validated: bool
    reason: str | None = None


def _reserved_percent(cost_ms: float, frame_budget_ms: float) -> float:
    """Convert a component's cost in milliseconds to a percentage of the frame budget."""
    return cost_ms / frame_budget_ms * 100.0


def _usable_percent(board: BoardProfile, role: str, reserve: float) -> float:
    """Return the CPU percentage available for component reservations on a role's MCU."""
    baseline = board.engine_host_baseline if role == "engine-host" else board.satellite_baseline
    return 100.0 - baseline.cpu_percent - reserve


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
    the largest single component cannot fit on a fresh satellite MCU.
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

    engine_usable = _usable_percent(board, "engine-host", reserve)
    satellite_usable = _usable_percent(board, "satellite", reserve)

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
            )
        bins.append(
            {
                "role": "engine-host",
                "usable": engine_usable,
                "used": engine_percent,
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
                )
            bins.append(
                {
                    "role": "satellite",
                    "usable": satellite_usable,
                    "used": percent,
                    "items": [(name, percent)],
                }
            )

    if not bins:
        bins.append({"role": "satellite", "usable": satellite_usable, "used": 0.0, "items": []})

    mcus = [
        McuAssignment(
            role=bin_["role"],
            components=[
                ComponentAssignment(name=name, reserved_percent=percent)
                for name, percent in bin_["items"]
            ],
            remaining_headroom_percent=bin_["usable"] - bin_["used"],
        )
        for bin_ in bins
    ]

    return AssignmentResult(
        feasible=True,
        mcus=mcus,
        co_location_validated=True,
    )

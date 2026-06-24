"""Shared helpers for on-device profiling scripts.

Every profiler under ``examples/hardware/profiling/`` prints a self-describing
header once at startup (board identity, target FPS, and the axes/values being
swept) and then a uniform per-interval stats line driven by a
``PerformanceTracker``. Centralizing both here keeps profiler output
comparable across components and boards.

This module is CircuitPython/MicroPython-safe (no per-frame allocation in the
hot path) but is also imported by CPython tooling, so optional hardware
modules are imported defensively.
"""

import gc
import sys

from effects.performance import PerformanceTracker

try:
    import board
except ImportError:
    board = None


def board_id() -> str:
    """Return a best-effort board identifier.

    Prefers ``board.board_id`` (CircuitPython). Falls back to
    ``sys.platform`` when running off-device (e.g. CPython during
    development).
    """
    if board is not None:
        return getattr(board, "board_id", "unknown-board")
    return sys.platform


def print_table_row(table: str, cells: list, driver: str = "-") -> None:
    """Print a paste-ready ``recorded-metrics.md`` row for ``table``.

    Prepends the row key every metrics table shares -- board, runtime, and
    driver -- to the component-specific ``cells`` the caller computed, then
    prints a ``__TABLE_ROW`` marker line (naming the target table so it is
    greppable in serial output) followed by the markdown row itself. Call once
    at the end of a sweep, after the constants have been aggregated.

    Args:
        table: Name of the target ``recorded-metrics.md`` table (e.g.
            ``"engine_component_costs"``).
        cells: The component-specific cell values, already formatted by the
            caller; unmeasured cells should be the literal ``"_TBD_"``.
        driver: The driver dimension for this row; ``"-"`` for components that
            are not driver-specific.
    """
    # Concatenation, not [a, b, *cells]: CircuitPython's parser rejects star
    # unpacking inside a list literal.
    row = format_table_row([board_id(), runtime_id(), driver] + list(cells))  # noqa: RUF005
    print(f"__TABLE_ROW table={table}")
    print(row)


def format_table_row(cells: list) -> str:
    """Join pre-formatted ``cells`` into a markdown table row.

    Each profiler formats its own cell values (it knows the units and the
    precision each constant needs) and unmeasured cells are passed as the
    literal ``"_TBD_"``; this helper only assembles them into a paste-ready
    ``| a | b | c |`` row for the ``recorded-metrics.md`` tables.
    """
    return "| " + " | ".join(str(cell) for cell in cells) + " |"


def format_runtime_id(name: str, version: tuple) -> str:
    """Format an implementation name and version into the table key style.

    The ``recorded-metrics.md`` tables key every row by runtime as
    ``circuitpython_10_0_3`` (name and dotted version joined with
    underscores). This builds that key from ``sys.implementation.name`` and
    ``sys.implementation.version`` so emitted rows drop straight into the
    table.
    """
    # Build the parts list without star unpacking -- CircuitPython's parser
    # rejects [name, *(...)] inside a list literal.
    parts = [name]
    for part in version[:3]:
        parts.append(str(part))
    return "_".join(parts)


def runtime_id() -> str:
    """Return this interpreter's runtime key (e.g. ``circuitpython_10_0_3``)."""
    impl = sys.implementation
    return format_runtime_id(impl.name, impl.version)


def linear_fit(xs: list[float], ys: list[float]) -> tuple[float, float]:
    """Least-squares fit of ``ys`` against ``xs``, returning ``(slope, intercept)``.

    Profilers sweep one axis (rule count, pixel count, concurrent voices, ...)
    and record the steady-state per-tick cost at each point. The slope is the
    measured marginal per-unit cost; the intercept is the fixed cost at zero
    units. Both are reported in the paste-ready table row so the constants
    never have to be eyeballed from raw stats lines.

    Args:
        xs: The swept independent values (e.g. rule counts).
        ys: The measured costs at each ``xs`` point, same length and order.

    Returns:
        ``(slope, intercept)`` of the best-fit line. With a single point the
        slope is ``0.0`` and the intercept is that point's ``y`` (no slope is
        defined from one sample).
    """
    n = len(xs)
    sum_x = sum(xs)
    sum_y = sum(ys)
    sum_xx = sum(x * x for x in xs)
    sum_xy = sum(x * y for x, y in zip(xs, ys))
    denominator = n * sum_xx - sum_x * sum_x
    if denominator == 0:
        # All xs identical (e.g. a single point): no slope is defined.
        return 0.0, sum_y / n
    slope = (n * sum_xy - sum_x * sum_y) / denominator
    intercept = (sum_y - slope * sum_x) / n
    return slope, intercept


def print_profile_header(
    component: str,
    sweep_axes: list[str],
    sweep_values: list[object],
    target_fps: float,
) -> None:
    """Print a self-describing header line for a profiling run.

    Call once at startup, before the profiling loop begins.

    Args:
        component: Name of the component or mode being profiled
            (e.g. ``"baseline.engine_host"``).
        sweep_axes: Names of the parameters being varied across the run
            (e.g. ``["element", "level"]``). Pass an empty list for profilers
            that do not sweep anything.
        sweep_values: Values corresponding to ``sweep_axes``, in the same
            order. Must be the same length as ``sweep_axes``.
        target_fps: The frame rate this profiler is trying to sustain.
    """
    sweep_parts = ", ".join(f"{axis}={value}" for axis, value in zip(sweep_axes, sweep_values))
    impl = sys.implementation
    impl_version = ".".join(str(part) for part in impl.version[:3])
    print(
        f"__PROFILE component={component}, "
        f"sweep=[{sweep_parts}], "
        f"target_fps={target_fps:.2f}, "
        f"board={board_id()}, "
        f"impl={impl.name} {impl_version}, "
        f"Mem Free: {gc.mem_free()}B"
    )


def print_stats_line(perf: PerformanceTracker, **extra: object) -> None:
    """Print the uniform per-interval profiling stats line (``__STATS``).

    This is the single profiling stats line: it reports the full set of fields
    ``PerformanceTracker`` accumulates (FPS, average update/render time, GC
    delta average/last/peak, allocation average, heap used/free, and peak
    frame time) plus any profiler-specific ``extra`` keyword values (e.g.
    ``cpu_percent``), so every profiler's output parses the same way.

    Call once when ``perf.complete_frame()`` returns ``True``. The FPS and
    memory snapshot are read from the frame ``complete_frame`` just closed
    (via ``perf.last_frame_end`` / ``perf.last_mem_used`` /
    ``perf.last_mem_free``), so no second clock or heap sample is taken here.
    """
    extra_parts = ", ".join(f"{name}={value}" for name, value in extra.items())
    frames = perf.frame_count
    elapsed = perf.last_frame_end - perf.start_time
    fps = frames / elapsed if elapsed > 0 else 0.0
    print(
        f"__STATS FPS: {fps:.2f}, "
        f"Update Time: {perf.update_time_total / frames:.4f}s, "
        f"Render Time: {perf.render_time_total / frames:.4f}s, "
        f"Mem Delta Avg: {perf.memory_delta_total / frames:.2f}B, "
        f"Mem Alloc Avg: {perf.memory_allocated_total / frames:.2f}B, "
        f"Mem Delta Last: {perf.last_memory_delta}B, "
        f"Mem Delta Peak: {perf.memory_delta_peak}B, "
        f"Mem Used: {perf.last_mem_used}B, "
        f"Mem Free: {perf.last_mem_free}B, "
        f"Frame Time Peak: {perf.frame_time_peak:.4f}s"
        + (f", {extra_parts}" if extra_parts else "")
    )

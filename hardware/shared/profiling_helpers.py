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


def stats_due(perf: PerformanceTracker, current_time: float) -> bool:
    """Return whether ``current_time`` has reached ``perf``'s next log interval.

    Call before ``perf.complete_frame(current_time)`` (which advances
    ``next_log_time``) to decide whether to print extra profiler-specific
    fields alongside ``perf``'s own stats line for this frame.
    """
    return current_time > perf.next_log_time


def print_stats_line(perf: PerformanceTracker, current_time: float, **extra: object) -> None:
    """Print the uniform per-interval profiling stats line.

    Mirrors the fields ``PerformanceTracker`` already tracks (FPS, average
    update/render time, GC delta/peak, free heap, and peak frame time) plus
    any profiler-specific ``extra`` keyword values (e.g. ``cpu_percent``),
    so every profiler's output can be parsed the same way.

    Call once per frame, immediately *before* ``perf.complete_frame(current_time)``
    (which advances ``perf``'s bookkeeping for the next interval), and only
    when ``stats_due(perf, current_time)`` is ``True``.
    """
    extra_parts = ", ".join(f"{name}={value}" for name, value in extra.items())
    fps = perf.frame_count / (current_time - perf.start_time)
    print(
        f"__STATS FPS: {fps:.2f}, "
        f"Update Time: {perf.update_time_total / perf.frame_count:.4f}s, "
        f"Render Time: {perf.render_time_total / perf.frame_count:.4f}s, "
        f"Mem Delta Avg: {perf.memory_delta_total / perf.frame_count:.2f}B, "
        f"Mem Delta Peak: {perf.memory_delta_peak}B, "
        f"Mem Free: {gc.mem_free()}B, "
        f"Frame Time Peak: {perf.frame_time_peak:.4f}s"
        + (f", {extra_parts}" if extra_parts else "")
    )

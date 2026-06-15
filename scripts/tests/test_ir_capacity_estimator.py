"""Behaviour-driven tests for the IR-receive deadline constraint added by the
capacity estimator's receiver model (see `docs/hardware/capacity-model.md` and #397).

These tests use synthetic board/prop constants (not real hardware numbers) and
assert assignment *decisions* (deadline pass/conflict, buffer-depth relief) rather
than the internal bin-packing algorithm.
"""

import pytest

from scripts.capacity.estimator import assign
from scripts.capacity.profiles import (
    BoardProfile,
    EngineComponent,
    McuBaseline,
    PixelScopeComponent,
    PropProfile,
    ReceiverComponent,
)

# 24 FPS -> frame_budget_ms ~= 41.6667ms
SYNTHETIC_BOARD = BoardProfile(
    name="synthetic-board",
    runtime="circuitpython",
    target_fps=24,
    peripherals=("neopixel",),
    total_free_heap_bytes=200_000,
    engine_host_baseline=McuBaseline(cpu_percent=10.0, heap_bytes=20_000),
    satellite_baseline=McuBaseline(cpu_percent=5.0, heap_bytes=10_000),
    headroom_reserve_percent=20.0,
)


def make_engine(*, remote_mcus: int = 0) -> EngineComponent:
    """Build a synthetic engine component: tick_fixed=2.0, per_rule=0.5, per_event=0.1,
    router_overhead=1.0, with 4 rules and 2 events per tick.
    """
    return EngineComponent(
        name="engine",
        tick_fixed_ms=2.0,
        per_rule_ms=0.5,
        per_event_ms=0.1,
        router_overhead_ms=1.0,
        rules=4,
        events_per_tick=2,
        remote_mcus=remote_mcus,
    )


def make_ir_rx(
    *,
    buffer_depth: int = 32,
    incoming_rate_hz: float = 1000.0,
    worst_case_frame_ms: float = 10.0,
) -> ReceiverComponent:
    """Build a synthetic IR-rx component modeling the fixed 4-receiver `InfraredMultiReceiver`.

    `cost_ms` is the `fixed_drain` per-tick polling cost (low and constant -- the
    4 receivers are not a deployment axis).
    """
    return ReceiverComponent(
        name="ir-rx",
        cost_ms=0.5,
        base_footprint_bytes=2_000,
        bytes_per_buffer_slot=4,
        buffer_depth=buffer_depth,
        incoming_rate_hz=incoming_rate_hz,
        worst_case_frame_ms=worst_case_frame_ms,
    )


# ---------------------------------------------------------------------------
# Deadline derivation and pass case
# ---------------------------------------------------------------------------


def test_max_frame_ms_is_derived_from_buffer_depth_and_incoming_rate():
    """max_frame_ms == buffer_depth / incoming_rate_hz * 1000, not a declared constant."""
    ir_rx = make_ir_rx(buffer_depth=32, incoming_rate_hz=1000.0, worst_case_frame_ms=10.0)

    # 32 / 1000 * 1000 = 32ms
    assert ir_rx.max_frame_ms == pytest.approx(32.0)


def test_receiver_within_its_deadline_is_feasible():
    """A receiver whose worst-case frame is comfortably under max_frame_ms co-locates fine."""
    engine = make_engine()
    # max_frame_ms = 32 / 1000 * 1000 = 32ms; worst_case_frame_ms = 10ms <= 32ms
    ir_rx = make_ir_rx(buffer_depth=32, incoming_rate_hz=1000.0, worst_case_frame_ms=10.0)
    prop = PropProfile(name="ir-prop", components=[engine, ir_rx])

    result = assign(prop, SYNTHETIC_BOARD)

    assert result.feasible
    assert result.conflict_type is None
    placed = {c.name for c in result.mcus[0].components}
    assert placed == {"engine", "ir-rx"}


# ---------------------------------------------------------------------------
# Deadline dominates budget
# ---------------------------------------------------------------------------


def test_receiver_whose_worst_case_frame_blows_its_deadline_is_rejected():
    """A receiver whose worst-case frame exceeds max_frame_ms is rejected even though
    CPU reservation would have fit."""
    engine = make_engine()
    # max_frame_ms = 32 / 1000 * 1000 = 32ms; worst_case_frame_ms = 50ms > 32ms
    ir_rx = make_ir_rx(buffer_depth=32, incoming_rate_hz=1000.0, worst_case_frame_ms=50.0)
    prop = PropProfile(name="ir-prop", components=[engine, ir_rx])

    result = assign(prop, SYNTHETIC_BOARD)

    assert not result.feasible
    assert result.mcus == []
    assert result.conflict_type == "deadline"
    assert "ir-rx" in result.reason
    assert "max_frame_ms" in result.reason


def test_heavy_pixel_load_that_fits_cpu_is_still_rejected_when_deadline_blows():
    """A receiver + heavy pixel load that fits on CPU is still rejected when the
    worst-case frame blows the deadline -- the deadline dominates the CPU budget."""
    engine = make_engine()
    # max_frame_ms = 32 / 1000 * 1000 = 32ms; worst_case_frame_ms = 50ms > 32ms
    ir_rx = make_ir_rx(buffer_depth=32, incoming_rate_hz=1000.0, worst_case_frame_ms=50.0)
    # Heavy pixel scope, but cost_ms = 0.05 * 100 + 1.0 = 6ms -> 14.4% reservation,
    # which comfortably fits the engine-host's usable CPU budget (70%) alongside the
    # engine (~14.88%) and ir-rx (0.5/41.6667*100 ~= 1.2%).
    heavy_pixels = PixelScopeComponent(
        name="ring",
        driver="neopixel_pwm",
        pixel_count=100,
        worst_case_effect_per_pixel_ms=0.05,
        flush_ms=1.0,
    )
    prop = PropProfile(name="ir-prop", components=[engine, ir_rx, heavy_pixels])

    result = assign(prop, SYNTHETIC_BOARD)

    assert not result.feasible
    assert result.conflict_type == "deadline"


# ---------------------------------------------------------------------------
# Buffer-depth relief
# ---------------------------------------------------------------------------


def test_raising_buffer_depth_relaxes_the_deadline_and_flips_assignment_to_feasible():
    """Raising buffer_depth raises max_frame_ms, relieving an otherwise-rejected
    deadline -- and increases memory footprint via the memory constraint."""
    engine = make_engine()
    # Shallow buffer: max_frame_ms = 32 / 1000 * 1000 = 32ms; worst_case_frame_ms = 50ms
    # -> 50ms > 32ms, deadline conflict.
    shallow_ir_rx = make_ir_rx(buffer_depth=32, incoming_rate_hz=1000.0, worst_case_frame_ms=50.0)
    # Deep buffer: max_frame_ms = 64 / 1000 * 1000 = 64ms; worst_case_frame_ms = 50ms
    # -> 50ms <= 64ms, feasible.
    deep_ir_rx = make_ir_rx(buffer_depth=64, incoming_rate_hz=1000.0, worst_case_frame_ms=50.0)

    shallow_prop = PropProfile(name="ir-prop", components=[engine, shallow_ir_rx])
    deep_prop = PropProfile(name="ir-prop", components=[engine, deep_ir_rx])

    shallow_result = assign(shallow_prop, SYNTHETIC_BOARD)
    deep_result = assign(deep_prop, SYNTHETIC_BOARD)

    assert not shallow_result.feasible
    assert shallow_result.conflict_type == "deadline"

    assert deep_result.feasible
    assert deep_result.conflict_type is None

    # Raising buffer_depth also raises memory_footprint_bytes (RAM-for-deadline trade-off).
    assert deep_ir_rx.memory_footprint_bytes > shallow_ir_rx.memory_footprint_bytes

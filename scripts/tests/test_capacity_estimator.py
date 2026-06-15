"""Behaviour-driven tests for the capacity estimator walking skeleton.

These tests use synthetic board/prop constants (not real hardware numbers) and assert
assignment *decisions* (fits on N MCUs, headroom %, infeasible reason) rather than the
internal bin-packing algorithm.
"""

import pytest

from scripts.capacity.estimator import assign
from scripts.capacity.profiles import (
    BoardProfile,
    EngineComponent,
    McuBaseline,
    PropProfile,
    ReceiverComponent,
    SimpleComponent,
)

# ---------------------------------------------------------------------------
# Synthetic board profile
# ---------------------------------------------------------------------------

# 24 FPS -> frame_budget_ms ~= 41.67ms
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


def test_workload_within_memory_budget_is_feasible_with_memory_headroom():
    """A workload whose summed footprint fits within the GC-margined heap budget passes."""
    engine = make_engine()
    engine_with_footprint = EngineComponent(
        name="engine",
        tick_fixed_ms=engine.tick_fixed_ms,
        per_rule_ms=engine.per_rule_ms,
        per_event_ms=engine.per_event_ms,
        router_overhead_ms=engine.router_overhead_ms,
        rules=engine.rules,
        events_per_tick=engine.events_per_tick,
        remote_mcus=engine.remote_mcus,
        memory_footprint_bytes=20_000,
    )
    prop = PropProfile(name="synthetic-prop", components=[engine_with_footprint])

    result = assign(prop, SYNTHETIC_BOARD)

    assert result.feasible
    assert result.conflict_type is None

    # usable_heap = total_free_heap(200_000) - engine_host_baseline.heap_bytes(20_000)
    #             - gc_margin_bytes(default 0 on SYNTHETIC_BOARD) = 180_000
    # summed footprint = 20_000 <= 180_000
    mcu = result.mcus[0]
    assert mcu.remaining_heap_bytes == pytest.approx(160_000)


def test_workload_within_cpu_budget_but_exceeding_memory_budget_is_a_memory_conflict():
    """A workload that fits the CPU budget but overflows the GC-margined heap is rejected."""
    engine = make_engine()
    engine_with_footprint = EngineComponent(
        name="engine",
        tick_fixed_ms=engine.tick_fixed_ms,
        per_rule_ms=engine.per_rule_ms,
        per_event_ms=engine.per_event_ms,
        router_overhead_ms=engine.router_overhead_ms,
        rules=engine.rules,
        events_per_tick=engine.events_per_tick,
        remote_mcus=engine.remote_mcus,
        # engine-host usable heap = 200_000 - 20_000 (baseline) - 0 (gc margin) = 180_000
        # a 200_000-byte footprint comfortably exceeds that, while CPU reservation
        # (~10.08%) is well within the engine-host's usable CPU budget (70%).
        memory_footprint_bytes=200_000,
    )
    prop = PropProfile(name="synthetic-prop", components=[engine_with_footprint])

    result = assign(prop, SYNTHETIC_BOARD)

    assert not result.feasible
    assert result.mcus == []
    assert result.conflict_type == "memory"
    assert "memory footprint" in result.reason


def test_raising_receiver_buffer_depth_can_flip_a_feasible_assignment_to_memory_conflict():
    """Raising a receiver's buffer depth for deadline relief increases its footprint and
    can push an assignment over the GC-margined heap budget."""
    engine = make_engine()
    # engine-host usable heap = 200_000 - 20_000 (baseline) - 0 (gc margin) = 180_000
    # shallow receiver: 170_000 + 1_000 * 4 = 174_000 <= 180_000 -> feasible
    shallow_receiver = ReceiverComponent(
        name="ir-receiver",
        cost_ms=1.0,
        base_footprint_bytes=170_000,
        bytes_per_buffer_slot=1_000,
        buffer_depth=4,
    )
    # deep receiver: 170_000 + 1_000 * 12 = 182_000 > 180_000 -> memory conflict
    deep_receiver = ReceiverComponent(
        name="ir-receiver",
        cost_ms=1.0,
        base_footprint_bytes=170_000,
        bytes_per_buffer_slot=1_000,
        buffer_depth=12,
    )

    shallow_prop = PropProfile(name="synthetic-prop", components=[engine, shallow_receiver])
    deep_prop = PropProfile(name="synthetic-prop", components=[engine, deep_receiver])

    shallow_result = assign(shallow_prop, SYNTHETIC_BOARD)
    deep_result = assign(deep_prop, SYNTHETIC_BOARD)

    assert shallow_result.feasible
    assert not deep_result.feasible
    assert deep_result.conflict_type == "memory"


def test_gc_margin_is_configurable_per_board_and_can_cause_a_memory_conflict():
    """A board with a larger GC margin rejects a footprint that a smaller-margin board accepts."""
    engine = make_engine()
    # engine-host usable heap (no gc margin) = 200_000 - 20_000 = 180_000
    # footprint 175_000 fits with no margin, but a 10_000-byte gc margin shrinks
    # usable heap to 170_000, which the same footprint overflows.
    engine_with_footprint = EngineComponent(
        name="engine",
        tick_fixed_ms=engine.tick_fixed_ms,
        per_rule_ms=engine.per_rule_ms,
        per_event_ms=engine.per_event_ms,
        router_overhead_ms=engine.router_overhead_ms,
        rules=engine.rules,
        events_per_tick=engine.events_per_tick,
        remote_mcus=engine.remote_mcus,
        memory_footprint_bytes=175_000,
    )
    prop = PropProfile(name="synthetic-prop", components=[engine_with_footprint])

    no_margin_result = assign(prop, SYNTHETIC_BOARD)
    assert no_margin_result.feasible

    board_with_margin = BoardProfile(
        name=SYNTHETIC_BOARD.name,
        runtime=SYNTHETIC_BOARD.runtime,
        target_fps=SYNTHETIC_BOARD.target_fps,
        peripherals=SYNTHETIC_BOARD.peripherals,
        total_free_heap_bytes=SYNTHETIC_BOARD.total_free_heap_bytes,
        engine_host_baseline=SYNTHETIC_BOARD.engine_host_baseline,
        satellite_baseline=SYNTHETIC_BOARD.satellite_baseline,
        headroom_reserve_percent=SYNTHETIC_BOARD.headroom_reserve_percent,
        gc_margin_bytes=10_000,
    )

    margin_result = assign(prop, board_with_margin)
    assert not margin_result.feasible
    assert margin_result.conflict_type == "memory"


def test_single_engine_component_fits_on_one_mcu_with_expected_headroom():
    """A small engine workload fits on the engine-host MCU with predictable headroom."""
    engine = make_engine()
    prop = PropProfile(name="synthetic-prop", components=[engine])

    result = assign(prop, SYNTHETIC_BOARD)

    assert result.feasible
    assert len(result.mcus) == 1

    mcu = result.mcus[0]
    assert mcu.role == "engine-host"
    assert [c.name for c in mcu.components] == ["engine"]

    # cost_ms = 2.0 + 0.5*4 + 0.1*2 + 1.0*0 = 4.2ms
    # frame_budget_ms = 1000/24 ~= 41.6667ms
    # reserved% = 4.2 / 41.6667 * 100 ~= 10.08%
    assert mcu.components[0].reserved_percent == pytest.approx(10.08, abs=0.01)

    # usable budget = 100 - engine_host_baseline(10) - headroom_reserve(20) = 70
    # remaining headroom = 70 - reserved(10.08) = 59.92
    assert mcu.remaining_headroom_percent == pytest.approx(59.92, abs=0.01)

    assert result.co_location_validated


def test_lowering_headroom_reserve_admits_a_previously_rejected_workload():
    """A workload rejected under the default headroom reserve fits once it is lowered."""
    engine = make_engine()
    # A single component costing 32ms -> 32/41.6667*100 = 76.8% of the frame budget.
    # At the default 20% headroom reserve, satellite_usable = 100 - 5 - 20 = 75%,
    # so 76.8% does not fit anywhere and the prop is rejected.
    # Lowering the headroom reserve to 10% raises satellite_usable to 85%, which
    # admits it onto a satellite MCU alongside the engine-host.
    renderer = SimpleComponent(name="renderer", cost_ms=32.0)
    prop = PropProfile(name="synthetic-prop", components=[engine, renderer])

    default_result = assign(prop, SYNTHETIC_BOARD)
    assert not default_result.feasible
    assert "headroom reserve" in default_result.reason

    relaxed_result = assign(prop, SYNTHETIC_BOARD, headroom_reserve_percent=10.0)
    assert relaxed_result.feasible
    assert len(relaxed_result.mcus) == 2
    placed_components = {c.name for mcu in relaxed_result.mcus for c in mcu.components}
    assert placed_components == {"engine", "renderer"}


def test_engine_host_has_less_usable_budget_than_satellite_for_same_components():
    """The engine-host's baseline deduction leaves it less headroom than a satellite."""
    engine = make_engine()
    prop = PropProfile(name="synthetic-prop", components=[engine])

    result = assign(prop, SYNTHETIC_BOARD)

    engine_mcu = result.mcus[0]
    assert engine_mcu.role == "engine-host"

    # engine-host usable = 100 - 10 (engine_host_baseline.cpu_percent) - 20 (headroom) = 70
    # satellite usable   = 100 - 5  (satellite_baseline.cpu_percent)  - 20 (headroom) = 75
    # The engine-host baseline (10%) is larger than the satellite baseline (5%), so for
    # the same reserved component cost, the engine-host has less remaining headroom.
    satellite_usable = 100.0 - SYNTHETIC_BOARD.satellite_baseline.cpu_percent - 20.0
    engine_usable = 100.0 - SYNTHETIC_BOARD.engine_host_baseline.cpu_percent - 20.0
    reserved = engine_mcu.components[0].reserved_percent

    assert engine_mcu.remaining_headroom_percent == pytest.approx(engine_usable - reserved)
    assert (engine_usable - reserved) < (satellite_usable - reserved)


def test_engine_router_cost_scales_with_remote_mcu_count():
    """Router overhead grows with `remote_mcus` and is charged to the engine's MCU."""
    base_engine = make_engine()
    two_remotes_engine = make_engine(remote_mcus=2)

    no_router_result = assign(PropProfile(name="prop", components=[base_engine]), SYNTHETIC_BOARD)
    with_router_result = assign(
        PropProfile(name="prop", components=[two_remotes_engine]), SYNTHETIC_BOARD
    )

    no_router_percent = no_router_result.mcus[0].components[0].reserved_percent
    with_router_percent = with_router_result.mcus[0].components[0].reserved_percent

    # router_overhead_ms (1.0) * remote_mcus (2) = 2ms extra -> 2/41.6667*100 = 4.8 points
    assert with_router_percent - no_router_percent == pytest.approx(4.8, abs=0.01)
    assert with_router_result.mcus[0].role == "engine-host"


def test_infeasible_workload_names_the_violated_constraint():
    """A component too large for even a fresh satellite is rejected with a named reason."""
    engine = make_engine()
    # 40ms -> 96% of frame budget, exceeds even a fresh satellite's usable budget (75%).
    oversized = SimpleComponent(name="oversized-renderer", cost_ms=40.0)
    prop = PropProfile(name="synthetic-prop", components=[engine, oversized])

    result = assign(prop, SYNTHETIC_BOARD)

    assert not result.feasible
    assert result.mcus == []
    assert not result.co_location_validated
    assert "oversized-renderer" in result.reason
    assert "satellite" in result.reason


def test_workload_exceeding_one_mcu_budget_splits_across_two_mcus():
    """A CPU-only prop that overflows the engine-host's usable budget spills onto a satellite."""
    engine = make_engine(remote_mcus=1)
    # engine cost = 2.0 + 0.5*4 + 0.1*2 + 1.0*1 = 5.2ms -> 5.2/41.6667*100 = 12.48%
    # engine-host usable budget = 100 - 10 (baseline) - 20 (headroom) = 70%
    # renderer-a costs 15ms -> 36% -- fits alongside the engine (12.48 + 36 = 48.48 <= 70)
    # renderer-b costs 25ms -> 60% -- does not fit in the remaining 21.52% on the
    # engine-host, so it spills to a satellite MCU
    renderer_a = SimpleComponent(name="renderer-a", cost_ms=15.0)
    renderer_b = SimpleComponent(name="renderer-b", cost_ms=25.0)
    prop = PropProfile(name="synthetic-prop", components=[engine, renderer_a, renderer_b])

    result = assign(prop, SYNTHETIC_BOARD)

    assert result.feasible
    assert len(result.mcus) == 2

    engine_mcu = next(mcu for mcu in result.mcus if mcu.role == "engine-host")
    satellite_mcu = next(mcu for mcu in result.mcus if mcu.role == "satellite")

    engine_components = {c.name for c in engine_mcu.components}
    satellite_components = {c.name for c in satellite_mcu.components}

    assert "engine" in engine_components
    assert engine_components | satellite_components == {"engine", "renderer-a", "renderer-b"}
    assert engine_components.isdisjoint(satellite_components)

    assert result.co_location_validated

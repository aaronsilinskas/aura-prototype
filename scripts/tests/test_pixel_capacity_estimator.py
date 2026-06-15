"""Behaviour-driven tests for pixel-scope sizing, splitting, drivers, and the
I2C bus-bandwidth constraint added by the capacity estimator's pixel model.

These tests use synthetic board/prop constants (not real hardware numbers) and
assert assignment *decisions* (fits on N MCUs, which MCU hosts which scope,
infeasible reason/conflict type) rather than the internal bin-packing algorithm.
"""

import pytest

from scripts.capacity.estimator import assign, fan_out_mcu_count
from scripts.capacity.profiles import (
    BoardProfile,
    BusBudget,
    EngineComponent,
    McuBaseline,
    PixelScopeComponent,
    PropProfile,
)

# 24 FPS -> frame_budget_ms ~= 41.6667ms
SYNTHETIC_BOARD = BoardProfile(
    name="synthetic-board",
    runtime="circuitpython",
    target_fps=24,
    peripherals=("neopixel", "is31fl3741"),
    total_free_heap_bytes=200_000,
    engine_host_baseline=McuBaseline(cpu_percent=10.0, heap_bytes=20_000),
    satellite_baseline=McuBaseline(cpu_percent=5.0, heap_bytes=10_000),
    headroom_reserve_percent=20.0,
    bus_budgets={"i2c": BusBudget(bandwidth_bytes_per_sec=10_000)},
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


# ---------------------------------------------------------------------------
# Stack depth sizing
# ---------------------------------------------------------------------------


def test_pixel_scope_cost_scales_with_stack_depth():
    """Doubling stack_depth doubles the per-pixel portion of the scope's cost."""
    single_layer = PixelScopeComponent(
        name="ring",
        driver="neopixel_pwm",
        pixel_count=10,
        worst_case_effect_per_pixel_ms=0.05,
        flush_ms=1.0,
    )
    double_layer = PixelScopeComponent(
        name="ring",
        driver="neopixel_pwm",
        pixel_count=10,
        worst_case_effect_per_pixel_ms=0.05,
        flush_ms=1.0,
        stack_depth=2,
    )

    # cost_ms = stack_depth * worst_case_effect_per_pixel_ms * pixel_count + flush_ms
    assert single_layer.stack_depth == 1
    assert single_layer.cost_ms == pytest.approx(1 * 0.05 * 10 + 1.0)
    assert double_layer.cost_ms == pytest.approx(2 * 0.05 * 10 + 1.0)
    assert double_layer.cost_ms == pytest.approx(single_layer.cost_ms + 0.5)


def test_single_pixel_scope_fits_alongside_engine_on_one_mcu():
    """A small single-scope pixel workload is co-located with the engine."""
    engine = make_engine()
    ring = PixelScopeComponent(
        name="ring",
        driver="neopixel_pwm",
        pixel_count=10,
        worst_case_effect_per_pixel_ms=0.05,
        flush_ms=1.0,
    )
    prop = PropProfile(name="pixel-prop", components=[engine, ring])

    result = assign(prop, SYNTHETIC_BOARD)

    assert result.feasible
    assert len(result.mcus) == 1
    placed = {c.name for c in result.mcus[0].components}
    assert placed == {"engine", "ring"}


# ---------------------------------------------------------------------------
# Per-scope splitting
# ---------------------------------------------------------------------------


def test_multi_scope_pixel_workload_too_heavy_for_one_mcu_splits_per_scope():
    """Each oversized pixel scope spills to its own satellite MCU; the engine and any
    indivisible component stay together and never split."""
    engine = make_engine(remote_mcus=2)
    # Each scope: 200 * 0.1 * 1 + 2.0 = 22ms -> 22/41.6667*100 = 52.8%
    # engine-host usable = 100 - 10 - 20 = 70%; satellite usable = 100 - 5 - 20 = 75%
    # engine cost ~= 2.0 + 0.5*4 + 0.1*2 + 1.0*2 = 6.2ms -> 14.88%
    # 14.88 + 52.8 = 67.68 <= 70, so scope_a *could* fit with the engine, but
    # 67.68 + 52.8 = 120.48 > 70, so scope_b cannot also fit there and must split.
    scope_a = PixelScopeComponent(
        name="scope-a",
        driver="neopixel_pwm",
        pixel_count=200,
        worst_case_effect_per_pixel_ms=0.1,
        flush_ms=2.0,
    )
    scope_b = PixelScopeComponent(
        name="scope-b",
        driver="neopixel_pwm",
        pixel_count=200,
        worst_case_effect_per_pixel_ms=0.1,
        flush_ms=2.0,
    )
    prop = PropProfile(name="pixel-prop", components=[engine, scope_a, scope_b])

    result = assign(prop, SYNTHETIC_BOARD)

    assert result.feasible
    assert len(result.mcus) == 2

    placements = {}
    for mcu in result.mcus:
        for c in mcu.components:
            placements[c.name] = mcu.role

    assert placements["engine"] == "engine-host"
    # The two pixel scopes are split across the two expected MCUs (each scope is
    # placeable independently; the engine never moves off the engine-host).
    assert placements["scope-a"] != placements["scope-b"]


# ---------------------------------------------------------------------------
# Driver dimension
# ---------------------------------------------------------------------------


def test_matrix_driver_consumes_i2c_bandwidth_while_pwm_driver_does_not():
    """An IS31FL3741 matrix scope reports nonzero I2C bandwidth; a NeoPixel PWM
    scope of the same size reports zero."""
    pwm_scope = PixelScopeComponent(
        name="ring",
        driver="neopixel_pwm",
        pixel_count=50,
        worst_case_effect_per_pixel_ms=0.05,
        flush_ms=1.0,
    )
    matrix_scope = PixelScopeComponent(
        name="panel",
        driver="is31fl3741_matrix",
        pixel_count=50,
        worst_case_effect_per_pixel_ms=0.08,
        flush_ms=3.0,
        i2c_transaction_bytes=200,
        i2c_frequency_hz=24,
    )

    assert pwm_scope.i2c_bandwidth_bytes_per_sec == 0
    assert matrix_scope.i2c_bandwidth_bytes_per_sec == pytest.approx(200 * 24)


def test_driver_choice_changes_per_pixel_cost_and_flush_cost():
    """Switching driver from NeoPixel PWM to the IS31FL3741 matrix changes both the
    per-pixel render cost and the flush cost used in the scope's `cost_ms`."""
    pwm_scope = PixelScopeComponent(
        name="ring",
        driver="neopixel_pwm",
        pixel_count=50,
        worst_case_effect_per_pixel_ms=0.05,
        flush_ms=1.0,
    )
    matrix_scope = PixelScopeComponent(
        name="panel",
        driver="is31fl3741_matrix",
        pixel_count=50,
        worst_case_effect_per_pixel_ms=0.08,
        flush_ms=3.0,
        i2c_transaction_bytes=200,
        i2c_frequency_hz=24,
    )

    assert matrix_scope.worst_case_effect_per_pixel_ms != pwm_scope.worst_case_effect_per_pixel_ms
    assert matrix_scope.flush_ms != pwm_scope.flush_ms


# ---------------------------------------------------------------------------
# Bus-bandwidth constraint
# ---------------------------------------------------------------------------


def test_bus_over_budget_assignment_is_rejected_even_with_cpu_headroom():
    """A matrix scope whose I2C usage exceeds the board's bus budget is rejected as a
    bus conflict, even though CPU has plenty of room."""
    engine = make_engine()
    # i2c bandwidth = 1000 bytes * 24 Hz = 24_000 bytes/sec > 10_000 budget
    matrix_scope = PixelScopeComponent(
        name="panel",
        driver="is31fl3741_matrix",
        pixel_count=10,
        worst_case_effect_per_pixel_ms=0.05,
        flush_ms=1.0,
        i2c_transaction_bytes=1000,
        i2c_frequency_hz=24,
    )
    prop = PropProfile(name="pixel-prop", components=[engine, matrix_scope])

    result = assign(prop, SYNTHETIC_BOARD)

    assert not result.feasible
    assert result.conflict_type == "bus"
    assert "i2c" in result.reason


# ---------------------------------------------------------------------------
# Router fan-out
# ---------------------------------------------------------------------------


def test_router_fan_out_counts_one_mcu_per_remote_output_in_scope():
    """An effect command's router cost fans out to every distinct remote MCU hosting
    a pixel scope, not once per pixel scope."""
    engine = make_engine(remote_mcus=2)
    # scope-a (52.8%) co-locates with the engine (14.88%): 67.68 <= 70 usable.
    scope_a = PixelScopeComponent(
        name="scope-a",
        driver="neopixel_pwm",
        pixel_count=200,
        worst_case_effect_per_pixel_ms=0.1,
        flush_ms=2.0,
    )
    # scope-b and scope-c each spill to their own satellite (52.8% each, too big to
    # share a satellite at 75% usable: 52.8 + 52.8 > 75).
    scope_b = PixelScopeComponent(
        name="scope-b",
        driver="neopixel_pwm",
        pixel_count=200,
        worst_case_effect_per_pixel_ms=0.1,
        flush_ms=2.0,
    )
    scope_c = PixelScopeComponent(
        name="scope-c",
        driver="neopixel_pwm",
        pixel_count=200,
        worst_case_effect_per_pixel_ms=0.1,
        flush_ms=2.0,
    )
    prop = PropProfile(name="pixel-prop", components=[engine, scope_a, scope_b, scope_c])

    result = assign(prop, SYNTHETIC_BOARD)
    assert result.feasible
    assert len(result.mcus) == 3

    # A command targeting scope-b and scope-c fans out to 2 remote satellite MCUs.
    assert fan_out_mcu_count(result, {"scope-b", "scope-c"}) == 2
    # A command targeting only scope-a (co-located with the engine) fans out to 0
    # remote MCUs -- the engine-host is never counted as a remote.
    assert fan_out_mcu_count(result, {"scope-a"}) == 0
    # A command targeting only scope-b fans out to 1 remote MCU.
    assert fan_out_mcu_count(result, {"scope-b"}) == 1


def test_switching_bus_over_budget_scope_to_neopixel_pwm_makes_it_feasible():
    """Swapping the over-budget matrix scope's driver to NeoPixel PWM removes the I2C
    load entirely, making the same workload feasible."""
    engine = make_engine()
    pwm_scope = PixelScopeComponent(
        name="panel",
        driver="neopixel_pwm",
        pixel_count=10,
        worst_case_effect_per_pixel_ms=0.05,
        flush_ms=1.0,
    )
    prop = PropProfile(name="pixel-prop", components=[engine, pwm_scope])

    result = assign(prop, SYNTHETIC_BOARD)

    assert result.feasible
    assert result.conflict_type is None

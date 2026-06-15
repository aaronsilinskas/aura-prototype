"""Behaviour-driven tests for the radio-tx/rx components added by #399.

Radio-tx and radio-rx carry **uncalibrated, datasheet-seeded** constants for the
RFM69HCW (see `docs/hardware/capacity-model.md`) so the estimator's deployment math
covers all 8 components even though the radio transport seam (driver + profilers) is
deferred to a follow-on PRD. These tests use synthetic/seed constants and assert
assignment *decisions* (radio entries participate, deadline math, uncalibrated flag
surfaced) rather than the internal bin-packing algorithm.
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

# 24 FPS -> frame_budget_ms ~= 41.6667ms
SYNTHETIC_BOARD = BoardProfile(
    name="synthetic-board",
    runtime="circuitpython",
    target_fps=24,
    peripherals=("neopixel", "spi"),
    total_free_heap_bytes=200_000,
    engine_host_baseline=McuBaseline(cpu_percent=10.0, heap_bytes=20_000),
    satellite_baseline=McuBaseline(cpu_percent=5.0, heap_bytes=10_000),
    headroom_reserve_percent=20.0,
)

# RFM69HCW datasheet-seeded constants (uncalibrated -- see capacity-model.md).
# 66-byte FIFO, ~31,250 B/s at 250kbps GFSK -> FIFO fills in 66 / 31250 * 1000 ~= 2.1ms.
RFM69_FIFO_DEPTH = 66
RFM69_INCOMING_RATE_BYTES_PER_SEC = 31_250


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


def make_radio_tx(*, cost_ms: float = 0.1) -> SimpleComponent:
    """Build an uncalibrated radio-tx component: a near-zero average CPU cost,
    seeded from the RFM69HCW datasheet (SPI write to the FIFO is fast/infrequent).
    """
    return SimpleComponent(
        name="radio-tx",
        cost_ms=cost_ms,
        memory_footprint_bytes=200,
        peripherals_required={"spi": 1},
        uncalibrated=True,
    )


def make_radio_rx(
    *,
    buffer_depth: int = RFM69_FIFO_DEPTH,
    incoming_rate_hz: float = RFM69_INCOMING_RATE_BYTES_PER_SEC,
    worst_case_frame_ms: float = 1.0,
) -> ReceiverComponent:
    """Build an uncalibrated radio-rx component: hard-real-time deadline model
    (`buffer_depth / incoming_rate_hz`) reused from IR-rx, with the RFM69HCW's
    66-byte FIFO as the buffer depth.
    """
    return ReceiverComponent(
        name="radio-rx",
        cost_ms=0.2,
        base_footprint_bytes=200,
        bytes_per_buffer_slot=1,
        buffer_depth=buffer_depth,
        incoming_rate_hz=incoming_rate_hz,
        worst_case_frame_ms=worst_case_frame_ms,
        peripherals_required={"spi": 1},
        uncalibrated=True,
    )


# ---------------------------------------------------------------------------
# Radio entries participate in assignment
# ---------------------------------------------------------------------------


def test_radio_tx_and_rx_participate_in_a_feasible_assignment():
    """Radio-tx and radio-rx are placed alongside the engine using seed constants."""
    engine = make_engine()
    radio_tx = make_radio_tx()
    radio_rx = make_radio_rx()
    prop = PropProfile(name="radio-prop", components=[engine, radio_tx, radio_rx])

    result = assign(prop, SYNTHETIC_BOARD)

    assert result.feasible
    assert result.conflict_type is None
    placed = {c.name for c in result.mcus[0].components}
    assert placed == {"engine", "radio-tx", "radio-rx"}


def test_radio_components_are_flagged_uncalibrated_in_assignment_output():
    """Assignment output surfaces the uncalibrated flag for radio entries, so reports
    can distinguish measured from seed constants."""
    engine = make_engine()
    radio_tx = make_radio_tx()
    radio_rx = make_radio_rx()
    prop = PropProfile(name="radio-prop", components=[engine, radio_tx, radio_rx])

    result = assign(prop, SYNTHETIC_BOARD)

    by_name = {c.name: c for c in result.mcus[0].components}
    assert by_name["radio-tx"].uncalibrated is True
    assert by_name["radio-rx"].uncalibrated is True
    assert by_name["engine"].uncalibrated is False


# ---------------------------------------------------------------------------
# Radio-rx deadline model: buffer_depth / incoming_rate_hz, FIFO depth as buffer depth
# ---------------------------------------------------------------------------


def test_radio_rx_max_frame_ms_is_derived_from_rfm69_fifo_depth_and_incoming_rate():
    """max_frame_ms == FIFO depth (66 bytes) / incoming_rate_hz * 1000, seeded from the
    RFM69HCW datasheet (~31,250 B/s at 250kbps GFSK -> FIFO fills in ~2.1ms)."""
    radio_rx = make_radio_rx()

    assert radio_rx.max_frame_ms == pytest.approx(2.112, rel=1e-3)


def test_radio_rx_whose_worst_case_frame_blows_its_tight_deadline_is_rejected():
    """The RFM69HCW's ~2.1ms FIFO-fill deadline is tight -- a worst-case frame that
    exceeds it is rejected even though CPU reservation would have fit."""
    engine = make_engine()
    # max_frame_ms ~= 2.112ms; worst_case_frame_ms = 5.0ms > 2.112ms
    radio_rx = make_radio_rx(worst_case_frame_ms=5.0)
    prop = PropProfile(name="radio-prop", components=[engine, radio_rx])

    result = assign(prop, SYNTHETIC_BOARD)

    assert not result.feasible
    assert result.conflict_type == "deadline"
    assert "radio-rx" in result.reason
    assert "max_frame_ms" in result.reason


def test_raising_radio_rx_buffer_depth_relaxes_the_tight_fifo_deadline():
    """Streaming reads (FifoNotEmpty/FifoThreshold) relax the tight FIFO-fill ceiling
    by effectively raising the buffer depth the estimator can absorb before overflow."""
    engine = make_engine()
    # Shallow (raw FIFO): max_frame_ms ~= 2.112ms; worst_case_frame_ms = 5.0ms -> conflict.
    shallow_radio_rx = make_radio_rx(buffer_depth=RFM69_FIFO_DEPTH, worst_case_frame_ms=5.0)
    # Deep (streaming reads relax the ceiling): max_frame_ms ~= 8.45ms >= 5.0ms -> feasible.
    deep_radio_rx = make_radio_rx(buffer_depth=RFM69_FIFO_DEPTH * 4, worst_case_frame_ms=5.0)

    shallow_prop = PropProfile(name="radio-prop", components=[engine, shallow_radio_rx])
    deep_prop = PropProfile(name="radio-prop", components=[engine, deep_radio_rx])

    shallow_result = assign(shallow_prop, SYNTHETIC_BOARD)
    deep_result = assign(deep_prop, SYNTHETIC_BOARD)

    assert not shallow_result.feasible
    assert shallow_result.conflict_type == "deadline"

    assert deep_result.feasible
    assert deep_result.conflict_type is None

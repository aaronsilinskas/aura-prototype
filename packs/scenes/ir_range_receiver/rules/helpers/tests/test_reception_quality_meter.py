"""Behaviour-driven tests for ``ReceptionQualityMeter`` -- the pure,
hardware-free IR link-quality classifier behind the ir_range_receiver scene.

Fabricates ``(sequence, timestamp)`` arrivals and per-tick ``now`` values
directly against the classifier; no ``GameState``/hardware involved.
"""

from __future__ import annotations

import tracemalloc

import pytest

from packs.scenes.ir_range_receiver.rules.helpers.reception_quality_meter import (
    COLOR_GREEN,
    COLOR_RED,
    COLOR_YELLOW,
    STATE_NONE,
    STATE_PARTIAL,
    STATE_PERFECT,
    ReceptionQualityMeter,
)


def _meter(window_seconds=1.0, silence_timeout=0.5, green_threshold=1.0) -> ReceptionQualityMeter:
    return ReceptionQualityMeter(
        window_seconds=window_seconds,
        silence_timeout=silence_timeout,
        green_threshold=green_threshold,
    )


def test_no_arrivals_ever_reports_none_state_and_red_after_boot():
    meter = _meter()

    quality = meter.evaluate(now=5.0)

    assert quality.state == STATE_NONE
    assert quality.color == COLOR_RED


def test_evaluate_allocates_nothing_on_the_no_packet_path():
    """The common per-tick heartbeat with no packet ever received (the boot
    state) must not allocate -- it is by far the most frequent tick."""
    meter = _meter()
    meter.evaluate(now=0.0)  # warm up

    tracemalloc.start()
    before = tracemalloc.take_snapshot()

    for i in range(100):
        meter.evaluate(now=float(i))

    after = tracemalloc.take_snapshot()
    tracemalloc.stop()

    diff = [
        stat
        for stat in after.compare_to(before, "lineno")
        if stat.traceback[0].filename.endswith("/reception_quality_meter.py") and stat.size_diff > 0
    ]
    assert not diff, f"Unexpected allocations in reception_quality_meter.py: {diff}"


def test_clean_in_order_stream_reports_perfect_state_at_full_progress():
    meter = _meter()

    for i, sequence in enumerate(range(0, 5)):
        meter.record(sequence=sequence, timestamp=i * 0.1)

    quality = meter.evaluate(now=0.45)

    assert quality.state == STATE_PERFECT
    assert quality.progress == pytest.approx(1.0)
    assert quality.color == COLOR_GREEN


def test_interleaved_gaps_report_partial_state_at_the_expected_reception_fraction():
    """Sequences 0,1,3,4,6 arrive (2 and 5 missing) -- span 0..6 is 7 slots,
    5 arrived, so 2 were dropped and the reception fraction is 5/7."""
    meter = _meter()

    for i, sequence in enumerate([0, 1, 3, 4, 6]):
        meter.record(sequence=sequence, timestamp=i * 0.1)

    quality = meter.evaluate(now=0.45)

    assert quality.state == STATE_PARTIAL
    assert quality.progress == pytest.approx(5 / 7)
    assert quality.color == COLOR_YELLOW
    assert quality.received == 5
    assert quality.dropped == 2


def test_window_scrolling_past_old_drops_recovers_to_perfect():
    """A bad early gap ages out of the 1s rolling window once enough clean,
    contiguous traffic follows -- the meter reports Perfect again without
    needing a special "reset" signal."""
    meter = _meter(window_seconds=1.0, silence_timeout=0.5)
    meter.record(sequence=0, timestamp=0.0)
    meter.record(sequence=5, timestamp=0.1)  # gap of 5 -- 4 dropped

    assert meter.evaluate(now=0.2).state == STATE_PARTIAL

    meter.record(sequence=6, timestamp=1.05)

    quality = meter.evaluate(now=1.1)

    assert quality.state == STATE_PERFECT
    assert quality.progress == pytest.approx(1.0)


def test_arrivals_then_silence_past_the_timeout_reports_none_state_and_red():
    meter = _meter(silence_timeout=0.5)
    meter.record(sequence=0, timestamp=0.0)
    meter.record(sequence=1, timestamp=0.1)

    assert meter.evaluate(now=0.15).state == STATE_PERFECT

    quality = meter.evaluate(now=0.61)  # 0.51s since the last arrival at 0.1

    assert quality.state == STATE_NONE
    assert quality.color == COLOR_RED


def test_sequence_wrap_from_255_to_0_is_treated_as_a_clean_contiguous_arrival():
    meter = _meter()
    meter.record(sequence=254, timestamp=0.0)
    meter.record(sequence=255, timestamp=0.1)
    meter.record(sequence=0, timestamp=0.2)
    meter.record(sequence=1, timestamp=0.3)

    quality = meter.evaluate(now=0.35)

    assert quality.state == STATE_PERFECT
    assert quality.progress == pytest.approx(1.0)


def test_a_gap_of_ten_is_counted_as_nine_dropped_packets():
    meter = _meter()
    meter.record(sequence=0, timestamp=0.0)
    meter.record(sequence=10, timestamp=0.1)

    quality = meter.evaluate(now=0.15)

    assert quality.received == 2
    assert quality.dropped == 9

"""Behaviour-driven tests for the pure IR receive-path telemetry summary."""

import tracemalloc

from hardware.shared.ir_telemetry import (
    IrTelemetryGate,
    IrTelemetrySnapshot,
    format_ir_telemetry_line,
)


def _snapshot(**overrides) -> IrTelemetrySnapshot:
    fields = {
        "pulses_seen": 0,
        "buffer_full_on_poll": 0,
        "packets_started": 0,
        "preamble_reject": 0,
        "mark_reject": 0,
        "space_reject": 0,
        "packets_completed": 0,
        "packets_surfaced": 0,
        "pulses_dropped_transmitting": 0,
    }
    fields.update(overrides)
    return IrTelemetrySnapshot(**fields)


# ---------------------------------------------------------------------------
# format_ir_telemetry_line
# ---------------------------------------------------------------------------


def test_format_line_includes_every_counter_in_pipeline_order():
    snapshot = _snapshot(
        pulses_seen=10,
        buffer_full_on_poll=1,
        packets_started=2,
        preamble_reject=3,
        mark_reject=4,
        space_reject=5,
        packets_completed=6,
        packets_surfaced=7,
        pulses_dropped_transmitting=9,
    )

    line = format_ir_telemetry_line(snapshot)

    # The order asserted below is the receive-pipeline order defined by the
    # issue, not an arbitrary field ordering.
    fields_in_order = [
        "pulses_seen=10",
        "buffer_full_on_poll=1",
        "packets_started=2",
        "preamble_reject=3",
        "mark_reject=4",
        "space_reject=5",
        "packets_completed=6",
        "packets_surfaced=7",
        "pulses_dropped_transmitting=9",
    ]
    positions = [line.index(field) for field in fields_in_order]
    assert positions == sorted(positions)


def test_format_line_matches_the_exact_serial_summary_string():
    """Regression pin: this is the exact line ``run_scene`` prints to the
    serial console, asserted byte-for-byte so a refactor cannot silently
    change what downstream log consumers see."""
    snapshot = _snapshot(
        pulses_seen=10,
        buffer_full_on_poll=1,
        packets_started=2,
        preamble_reject=3,
        mark_reject=4,
        space_reject=5,
        packets_completed=6,
        packets_surfaced=7,
        pulses_dropped_transmitting=9,
    )

    line = format_ir_telemetry_line(snapshot)

    assert line == (
        "ir: pulses_seen=10 buffer_full_on_poll=1 packets_started=2 "
        "preamble_reject=3 mark_reject=4 space_reject=5 packets_completed=6 "
        "packets_surfaced=7 pulses_dropped_transmitting=9"
    )


# ---------------------------------------------------------------------------
# IrTelemetryGate — change detection
# ---------------------------------------------------------------------------


def test_gate_returns_line_on_first_poll():
    """The very first poll has no prior baseline, so it always reports."""
    gate = IrTelemetryGate()

    result = gate.poll(_snapshot())

    assert result is not None


def test_gate_returns_none_when_nothing_changed_since_last_poll():
    gate = IrTelemetryGate()
    gate.poll(_snapshot())

    assert gate.poll(_snapshot()) is None


def test_gate_returns_line_when_a_counter_changed():
    gate = IrTelemetryGate()
    gate.poll(_snapshot())

    result = gate.poll(_snapshot(pulses_seen=1))

    assert result is not None
    assert "pulses_seen=1" in result


def test_gate_does_not_report_again_until_another_change():
    gate = IrTelemetryGate()
    gate.poll(_snapshot())
    gate.poll(_snapshot(packets_surfaced=1))

    assert gate.poll(_snapshot(packets_surfaced=1)) is None


def test_gate_returns_line_when_pulses_dropped_transmitting_changed():
    gate = IrTelemetryGate()
    gate.poll(_snapshot())

    result = gate.poll(_snapshot(pulses_dropped_transmitting=1))

    assert result is not None
    assert "pulses_dropped_transmitting=1" in result


def test_gate_does_not_report_again_until_pulses_dropped_transmitting_changes_further():
    gate = IrTelemetryGate()
    gate.poll(_snapshot())
    gate.poll(_snapshot(pulses_dropped_transmitting=1))

    assert gate.poll(_snapshot(pulses_dropped_transmitting=1)) is None


# ---------------------------------------------------------------------------
# IrTelemetryGate — no per-call allocation when nothing changed
# ---------------------------------------------------------------------------


def test_gate_poll_allocates_nothing_when_unchanged():
    """The no-pulse tick is the common hot path and must not allocate."""
    gate = IrTelemetryGate()
    snapshot = _snapshot()
    gate.poll(snapshot)  # warm up / establish baseline

    tracemalloc.start()
    before = tracemalloc.take_snapshot()

    for _ in range(100):
        gate.poll(snapshot)

    after = tracemalloc.take_snapshot()
    tracemalloc.stop()

    diff = [
        stat
        for stat in after.compare_to(before, "lineno")
        if "ir_telemetry.py" in stat.traceback[0].filename and stat.size_diff > 0
    ]
    assert not diff, f"Unexpected allocations in ir_telemetry.py during unchanged poll: {diff}"

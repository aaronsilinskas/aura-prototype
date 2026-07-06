"""Pure IR receive-path telemetry summary — no board imports, CPython-testable.

Formats the one-line-per-second serial summary that ``run_scene`` prints,
gated on a counter actually changing since the last poll. No ``pulseio``
import — safe on CPython, CircuitPython 10.x, and MicroPython.
"""

try:
    from typing import Final
except ImportError:
    pass  # Not available on all embedded runtimes

__all__ = ["IrTelemetryGate", "IrTelemetrySnapshot", "format_ir_telemetry_line"]


class IrTelemetrySnapshot:
    """One tick's worth of IR receive-path counters, in pipeline order.

    Plain value holder (no ``dataclasses`` — unavailable on constrained
    runtimes). ``FIELDS`` is the single ordered list of counter names —
    ``__slots__``, ``format_ir_telemetry_line``, and ``IrTelemetryGate`` all
    iterate it rather than re-enumerating the counters: ``pulses_seen ->
    buffer_full_on_poll -> packets_started -> rejected{preamble,mark,space}
    -> packets_completed -> packets_surfaced -> pulses_dropped_transmitting
    -> events_queued``.
    """

    FIELDS: Final = (
        "pulses_seen",
        "buffer_full_on_poll",
        "packets_started",
        "preamble_reject",
        "mark_reject",
        "space_reject",
        "packets_completed",
        "packets_surfaced",
        "pulses_dropped_transmitting",
        "events_queued",
    )

    __slots__ = FIELDS

    def __init__(
        self,
        pulses_seen: int,
        buffer_full_on_poll: int,
        packets_started: int,
        preamble_reject: int,
        mark_reject: int,
        space_reject: int,
        packets_completed: int,
        packets_surfaced: int,
        pulses_dropped_transmitting: int,
        events_queued: int,
    ) -> None:
        self.pulses_seen = pulses_seen
        self.buffer_full_on_poll = buffer_full_on_poll
        self.packets_started = packets_started
        self.preamble_reject = preamble_reject
        self.mark_reject = mark_reject
        self.space_reject = space_reject
        self.packets_completed = packets_completed
        self.packets_surfaced = packets_surfaced
        self.pulses_dropped_transmitting = pulses_dropped_transmitting
        self.events_queued = events_queued


def format_ir_telemetry_line(snapshot: IrTelemetrySnapshot) -> str:
    """Render *snapshot* as a single pipeline-ordered summary line.

    Args:
        snapshot: Counters for the current tick.

    Returns:
        A single-line string an operator can scan to find the stage where a
        shot was lost — a drop between adjacent counters names the lossy
        stage.
    """
    parts = ["ir:"]
    for field in IrTelemetrySnapshot.FIELDS:
        parts.append(field + "=" + str(getattr(snapshot, field)))
    return " ".join(parts)


class IrTelemetryGate:
    """Tracks the last-reported snapshot and reports only when a field changed.

    Holds a single reference to the last-reported ``IrTelemetrySnapshot``
    (``None`` until the first poll) rather than a per-field baseline mirror,
    so ``poll()`` never allocates when nothing changed — the common
    no-pulse tick.
    """

    __slots__ = ("_previous",)

    def __init__(self) -> None:
        self._previous = None

    def poll(self, snapshot: IrTelemetrySnapshot) -> str | None:
        """Compare *snapshot* to the last-reported snapshot.

        Args:
            snapshot: Current tick's counters.

        Returns:
            A formatted summary line if this is the first poll or any
            counter differs from the last-reported snapshot; ``None``
            otherwise (no allocation in that path).
        """
        previous = self._previous
        changed = previous is None
        if not changed:
            for field in IrTelemetrySnapshot.FIELDS:
                if getattr(snapshot, field) != getattr(previous, field):
                    changed = True
                    break

        if not changed:
            return None

        self._previous = snapshot

        return format_ir_telemetry_line(snapshot)

"""Pure IR receive-path telemetry summary — no board imports, CPython-testable.

Formats the one-line-per-second serial summary that ``run_scene`` prints,
gated on a counter actually changing since the last poll. No ``pulseio``
import — safe on CPython, CircuitPython 10.x, and MicroPython.
"""

__all__ = ["IrTelemetryGate", "IrTelemetrySnapshot", "format_ir_telemetry_line"]


class IrTelemetrySnapshot:
    """One tick's worth of IR receive-path counters, in pipeline order.

    Plain value holder (no ``dataclasses`` — unavailable on constrained
    runtimes); fields mirror the stage counters named in the issue:
    ``pulses_seen -> buffer_full_on_poll -> packets_started ->
    rejected{preamble,mark,space} -> packets_completed -> packets_surfaced
    -> events_queued``.
    """

    __slots__ = (
        "buffer_full_on_poll",
        "events_queued",
        "mark_reject",
        "packets_completed",
        "packets_started",
        "packets_surfaced",
        "preamble_reject",
        "pulses_seen",
        "space_reject",
    )

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
    return (
        "ir: pulses_seen="
        + str(snapshot.pulses_seen)
        + " buffer_full_on_poll="
        + str(snapshot.buffer_full_on_poll)
        + " packets_started="
        + str(snapshot.packets_started)
        + " preamble_reject="
        + str(snapshot.preamble_reject)
        + " mark_reject="
        + str(snapshot.mark_reject)
        + " space_reject="
        + str(snapshot.space_reject)
        + " packets_completed="
        + str(snapshot.packets_completed)
        + " packets_surfaced="
        + str(snapshot.packets_surfaced)
        + " events_queued="
        + str(snapshot.events_queued)
    )


class IrTelemetryGate:
    """Tracks the last-seen counters and reports only when one changed.

    Holds its own previous-snapshot fields as plain ``int`` attributes
    (pre-allocated in ``__init__``) so ``poll()`` never allocates when
    nothing changed — the common no-pulse tick.
    """

    __slots__ = (
        "_buffer_full_on_poll",
        "_events_queued",
        "_has_baseline",
        "_mark_reject",
        "_packets_completed",
        "_packets_started",
        "_packets_surfaced",
        "_preamble_reject",
        "_pulses_seen",
        "_space_reject",
    )

    def __init__(self) -> None:
        self._has_baseline = False
        self._pulses_seen = 0
        self._buffer_full_on_poll = 0
        self._packets_started = 0
        self._preamble_reject = 0
        self._mark_reject = 0
        self._space_reject = 0
        self._packets_completed = 0
        self._packets_surfaced = 0
        self._events_queued = 0

    def poll(self, snapshot: IrTelemetrySnapshot) -> str | None:
        """Compare *snapshot* to the last-reported counters.

        Args:
            snapshot: Current tick's counters.

        Returns:
            A formatted summary line if this is the first poll or any
            counter differs from the last-reported snapshot; ``None``
            otherwise (no allocation in that path).
        """
        changed = (
            not self._has_baseline
            or snapshot.pulses_seen != self._pulses_seen
            or snapshot.buffer_full_on_poll != self._buffer_full_on_poll
            or snapshot.packets_started != self._packets_started
            or snapshot.preamble_reject != self._preamble_reject
            or snapshot.mark_reject != self._mark_reject
            or snapshot.space_reject != self._space_reject
            or snapshot.packets_completed != self._packets_completed
            or snapshot.packets_surfaced != self._packets_surfaced
            or snapshot.events_queued != self._events_queued
        )
        if not changed:
            return None

        self._has_baseline = True
        self._pulses_seen = snapshot.pulses_seen
        self._buffer_full_on_poll = snapshot.buffer_full_on_poll
        self._packets_started = snapshot.packets_started
        self._preamble_reject = snapshot.preamble_reject
        self._mark_reject = snapshot.mark_reject
        self._space_reject = snapshot.space_reject
        self._packets_completed = snapshot.packets_completed
        self._packets_surfaced = snapshot.packets_surfaced
        self._events_queued = snapshot.events_queued

        return format_ir_telemetry_line(snapshot)

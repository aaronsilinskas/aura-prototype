"""Hardware-agnostic IR transport layer for the Aura platform.

Provides the ``PulseReader`` / ``PulseWriter`` port abstractions, the
``InfraredTransmitter``, and the ``InfraredSingleReceiver`` /
``InfraredMultiReceiver`` receivers built on top of the codec base classes from
``hardware.shared.ir_codecs.base``.

No ``pulseio`` import — safe on CPython, CircuitPython 10.x, and MicroPython.

Design notes
------------
- ``PulseReader`` and ``PulseWriter`` are plain base classes (not
  ``typing.Protocol``, which is unavailable on constrained runtimes).
- ``InfraredMultiReceiver.receive()`` is polled every tick.  All per-receiver
  scratch structures are pre-allocated in ``__init__`` and reused each call —
  the inner loop allocates nothing per tick.
"""

from array import array

from hardware.shared.ir_codecs.base import InfraredDecoder, InfraredEncoder
from hardware.shared.ir_telemetry import IrTelemetryGate, IrTelemetrySnapshot

try:
    from collections.abc import Callable
except ImportError:
    pass  # Not available on all embedded runtimes

# ---------------------------------------------------------------------------
# Port abstractions
# ---------------------------------------------------------------------------


class PulseWriter:
    """Port through which :class:`InfraredTransmitter` sends IR pulses.

    A plain base class — subclass and override :meth:`write_pulses` to
    connect to hardware (e.g. ``pulseio.PulseOut``) or a test fake.
    """

    def write_pulses(self, durations: "array[int] | list[int]") -> None:
        """Transmit a sequence of pulse durations in microseconds.

        Args:
            durations: Sequence of integer pulse durations (µs), alternating
                mark/space, starting with a mark.

        Raises:
            NotImplementedError: Always — subclasses must override.
        """
        raise NotImplementedError

    def is_busy(self) -> bool:
        """Return ``True`` while a previously started send is still outstanding.

        A truthful query, not a hard-coded constant — a blocking writer
        reports ``True`` only for the (externally unobservable, on a
        single-core runtime) duration of its blocking send; a non-blocking
        (e.g. DMA-backed) writer reports ``True`` until the hardware signals
        completion.

        Raises:
            NotImplementedError: Always — subclasses must override.
        """
        raise NotImplementedError


class PulseReader:
    """Port through which receivers consume IR pulses one at a time.

    A plain base class — subclass and override :meth:`read_pulse` to
    connect to hardware (e.g. ``pulseio.PulseIn``) or a test fake.

    Attributes:
        buffer_full_on_poll: Monotonic-since-boot count of reads that
            observed a full underlying buffer — a proxy for overrun pulse
            loss. Defaults to 0 so readers that cannot detect overrun (e.g.
            test fakes) still satisfy the telemetry contract.
    """

    # The IR receive-path telemetry counter this class owns — the read
    # source ``InfraredSourceReceiver.telemetry()`` sums across every reader
    # and the reset source ``reset_telemetry()`` zeroes on every reader.
    OWNED_TELEMETRY_FIELDS = ("buffer_full_on_poll",)

    buffer_full_on_poll: int = 0

    def read_pulse(self) -> "int | None":
        """Return the next available pulse duration in microseconds, or ``None``.

        The caller must be able to call this repeatedly without blocking —
        it returns ``None`` immediately when no pulse is available.

        Returns:
            Pulse duration in µs, or ``None`` if no pulse is ready.

        Raises:
            NotImplementedError: Always — subclasses must override.
        """
        raise NotImplementedError

    def reset_telemetry(self) -> None:
        """Zero ``buffer_full_on_poll``. No-op on the base — overridden by
        readers that track real telemetry (e.g. :class:`PulseInReader`)."""
        self.buffer_full_on_poll = 0


# ---------------------------------------------------------------------------
# IR transmit gate
# ---------------------------------------------------------------------------


class IrTransmitGate:
    """Coordinates transmit and receive so a device never decodes its own
    **self-echo** — the IR pulses its own receiver captures while its own
    emitter is lit.

    The single seam between an otherwise-decoupled transmitter and receiver:
    transmitters *drive* the gate (:meth:`begin_transmit` / :meth:`end_transmit`
    bracketing emission), the receiver *reads* it through the single
    :meth:`should_discard` query (:attr:`transmitting` stays exposed as a cheap,
    side-effect-free "is the emitter lit?" window for tests and telemetry).
    Neither side references the other.

    Tracks an active-emission depth (not a bare boolean) so suppression stays
    armed across concurrent or back-to-back emissions, falling to "not
    transmitting" only when the last active emission ends. ``__slots__`` —
    no per-instance dict, safe to construct once per device.
    """

    __slots__ = ("_depth", "_flush_pending")

    def __init__(self) -> None:
        self._depth: int = 0
        self._flush_pending: bool = False

    def begin_transmit(self) -> None:
        """Mark one emission as starting. Increments the active-emission depth."""
        self._depth += 1

    def end_transmit(self) -> None:
        """Mark one emission as ending.

        Decrements the active-emission depth (never below 0) and arms the
        one-shot flush latch so the receiver performs exactly one more
        drain-and-discard on its next poll.
        """
        if self._depth > 0:
            self._depth -= 1
        self._flush_pending = True

    @property
    def transmitting(self) -> bool:
        """``True`` while at least one emission is active."""
        return self._depth > 0

    def should_discard(self) -> bool:
        """Return whether the receiver should drain-and-discard this tick.

        The receiver's single self-echo query. Short-circuits ``True`` while
        transmitting *without* touching the flush latch, so the falling-edge
        one-shot is preserved for the tick after emission ends. Once idle,
        consumes the one-shot latch: ``True`` exactly once on the falling edge,
        then ``False``.
        """
        if self._depth > 0:
            return True
        if self._flush_pending:
            self._flush_pending = False
            return True
        return False


# ---------------------------------------------------------------------------
# Transmitter
# ---------------------------------------------------------------------------


class InfraredTransmitter:
    """Transmits IR payloads through a :class:`PulseWriter`, hiding whether the
    underlying write is blocking or non-blocking from callers — one class
    drives both kinds of writer.

    Send/poll model:
      - :meth:`send` starts the write immediately if the writer is idle; if
        busy, *data* is appended to an unbounded FIFO queue of buffered
        payloads instead of overwriting anything already queued.
      - :meth:`poll` must be called every tick. It does nothing while the
        writer is busy; once idle, it releases a deferred gate (see *Gate
        timing* below) and starts the oldest queued payload, if any.
      - Encoding happens exactly once per transmitted payload, at
        start-of-write — never per-tick.

    Gate timing:
      - Starting a write calls :meth:`IrTransmitGate.begin_transmit`, encodes,
        calls :meth:`PulseWriter.write_pulses`, arms the deferred-release
        flag, then calls :meth:`_release_gate_when_idle`. If the writer is
        already idle (a blocking writer finished synchronously)
        :meth:`IrTransmitGate.end_transmit` fires immediately — reproducing
        the original ``try``/``finally`` byte-for-byte. If the writer is
        still busy (e.g. DMA in flight) the flag stays armed and the next
        :meth:`poll` that observes idle releases it, via the same
        :meth:`_release_gate_when_idle`, before starting the oldest queued
        send.

    Error semantics:
      - An encode error raised while kicking off a write from :meth:`send`
        propagates immediately (the gate is still released via
        ``try``/``finally``).
      - An encode error on a payload that was queued surfaces later, from
        the :meth:`poll` call that attempts to start it — accepted for a
        fire-and-forget API. The failing payload is removed from the queue
        before the error propagates, so later polls keep draining the
        payloads queued after it.

    Args:
        pulse_writer: Hardware port that physically transmits pulses.
        encoder: :class:`~hardware.shared.ir_codecs.base.InfraredEncoder` subclass
            that converts bytes to a pulse-duration array.
        gate: :class:`IrTransmitGate` driven across the write so the receiver
            can suppress self-echo.
    """

    def __init__(
        self,
        pulse_writer: PulseWriter,
        encoder: InfraredEncoder,
        gate: "IrTransmitGate | None" = None,
    ) -> None:
        self._writer = pulse_writer
        self._encoder = encoder
        self._gate = gate
        self._pending_queue: list[bytes] = []
        self._gate_armed: bool = False

    def send(self, data: bytes) -> bool:
        """Start transmitting *data* if idle, else append it to the FIFO queue.

        While a write is outstanding (``PulseWriter.is_busy()`` is ``True``),
        *data* is appended to an unbounded FIFO queue of buffered payloads —
        nothing already queued is overwritten. No encoding happens for a
        queued payload until it is started (by :meth:`poll`, oldest first).

        Args:
            data: Opaque payload bytes to transmit.

        Returns:
            ``True`` only if *data* was fully transmitted synchronously —
            the writer was idle at entry *and* reports idle again
            immediately after :meth:`PulseWriter.write_pulses` returns (a
            blocking writer). ``False`` in every other case: the writer was
            busy at entry (*data* was appended to the queue), or the write
            started but is still outstanding on a non-blocking (e.g.
            DMA-backed) writer — started, not yet sent.
        """
        if self._writer.is_busy():
            self._pending_queue.append(data)
            return False
        self._start_write(data)
        return not self._writer.is_busy()

    def poll(self) -> bool:
        """Per-tick pump: release a deferred gate and start the oldest queued send.

        Must be called every tick. Does nothing while the writer reports
        busy. Once the writer reports idle, calls
        :meth:`_release_gate_when_idle` (fires the transmit gate's
        ``end_transmit`` if it was left armed by a non-blocking write), then
        pops and starts the oldest queued payload, if any (a no-op when the
        queue is empty).

        Returns:
            The writer's busy state evaluated at the end of the call — after
            any gate release and after starting a queued send, if one
            existed.

        Raises:
            Exception: Whatever the encoder raises, if a queued payload's
                encoding fails — surfaced here rather than at the original
                ``send()`` call. The failing payload is already popped from
                the queue, so later polls keep draining what follows it.
        """
        writer = self._writer
        if writer.is_busy():
            return True

        self._release_gate_when_idle()

        pending_queue = self._pending_queue
        if pending_queue:
            self._start_write(pending_queue.pop(0))

        return writer.is_busy()

    def _start_write(self, data: bytes) -> None:
        """Encode *data* and kick off the write, bracketing it with the gate.

        Args:
            data: Opaque payload bytes to transmit.
        """
        gate = self._gate
        if gate is None:
            pulses = self._encoder.encode(data)
            self._writer.write_pulses(pulses)
            return

        gate.begin_transmit()
        try:
            pulses = self._encoder.encode(data)
            self._writer.write_pulses(pulses)
        except Exception:
            gate.end_transmit()
            raise

        self._gate_armed = True
        self._release_gate_when_idle()

    def _release_gate_when_idle(self) -> None:
        """Fire the deferred ``end_transmit`` once the writer reports idle.

        No-op unless :attr:`_gate_armed` is set. A blocking writer is already
        idle by the time :meth:`_start_write` calls this, so the release
        happens inline; a non-blocking (e.g. DMA-backed) writer stays busy
        until a later :meth:`poll` observes idle and releases it there. Either
        way this is the sole place ``_gate_armed`` is cleared and
        ``end_transmit`` fires, so both writer kinds get identical self-echo
        suppression.
        """
        if not self._gate_armed or self._writer.is_busy():
            return
        self._gate_armed = False
        gate = self._gate
        if gate is not None:
            gate.end_transmit()


# ---------------------------------------------------------------------------
# Receiver base
# ---------------------------------------------------------------------------


class InfraredReceiver:
    """Abstract base for IR receivers.

    Subclasses implement :meth:`receive`, which must be polled every tick.
    Exposes telemetry attributes populated after each successful decode:
    ``last_signal_strength``, ``last_error_margin``, and
    ``last_best_receiver``.

    Defines the telemetry-counter contract for the whole IR receive path via
    :meth:`telemetry`/:meth:`telemetry_line` — every counter below defaults
    to 0 via :meth:`telemetry`'s ``getattr(self, name, 0)`` fallback, so any
    receiver (including test fakes with no counter attributes at all)
    satisfies the contract with no telemetry code. Concrete receivers (e.g.
    :class:`InfraredSingleReceiver`) override :meth:`telemetry` to report
    real, monotonic-since-boot counts; the counters below are not guaranteed
    to reflect those real counts directly — read them through
    :meth:`telemetry` instead.

    Attributes:
        pulses_seen: Count of pulses drained from the reader.
        packets_surfaced: Count of decoded packets returned by :meth:`receive`.
        packets_started: Decoder packets-started count.
        packets_completed: Decoder packets-completed count.
        preamble_reject: Decoder preamble-reject count.
        mark_reject: Decoder mark-reject count.
        space_reject: Decoder space-reject count.
        buffer_full_on_poll: Reader buffer-full-on-poll count.
        pulses_dropped_transmitting: Count of pulses drained and discarded
            under **drain-but-discard** while the :class:`IrTransmitGate` was
            transmitting or flushing. Kept out of ``pulses_seen``.
    """

    # The IR receive-path telemetry counters this class owns — read directly
    # off a receiver instance by :class:`InfraredSourceReceiver`'s
    # ``telemetry()``/``reset_telemetry()``, which sum/reset the
    # decoder-owned and reader-owned counters from the decoder and reader
    # lists instead.
    OWNED_TELEMETRY_FIELDS = ("pulses_seen", "packets_surfaced", "pulses_dropped_transmitting")

    def __init__(self) -> None:
        # Owns the change-gate for telemetry_line(). Distinct from a
        # transmit-gate-carrying subclass's self._gate (the IrTransmitGate).
        self._telemetry_gate = IrTelemetryGate()

    def reset_telemetry(self) -> None:
        """Zero every counter in the IR-path telemetry contract.

        Also resets :meth:`telemetry_line`'s change-gate baseline, so the
        next call reports unconditionally. Receivers that track real
        counters (e.g. :class:`InfraredSingleReceiver`) override this to
        also reset their decoder and reader.
        """
        self.pulses_seen = 0
        self.packets_surfaced = 0
        self.packets_started = 0
        self.packets_completed = 0
        self.preamble_reject = 0
        self.mark_reject = 0
        self.space_reject = 0
        self.buffer_full_on_poll = 0
        self.pulses_dropped_transmitting = 0
        self._telemetry_gate = IrTelemetryGate()

    def telemetry(self) -> IrTelemetrySnapshot:
        """Build a snapshot of every counter in the IR-path telemetry contract.

        Generic working default — iterates ``IrTelemetrySnapshot.FIELDS`` and
        reads each counter off ``self`` via ``getattr(self, name, 0)``, so
        bare/fake receivers satisfy the contract with no telemetry code.
        Concrete receivers (e.g. :class:`InfraredSingleReceiver`) override
        this to map each counter from its real source explicitly.

        Returns:
            The current tick's :class:`IrTelemetrySnapshot`.
        """
        return IrTelemetrySnapshot(*(getattr(self, name, 0) for name in IrTelemetrySnapshot.FIELDS))

    def telemetry_line(self) -> "str | None":
        """Return a change-gated one-line telemetry summary, or ``None``.

        Polls :meth:`telemetry` through this receiver's own
        :class:`IrTelemetryGate`, so callers (``run_scene``) only ever see a
        line when a counter changed since the last call.

        Returns:
            A formatted summary line, or ``None`` when no counter changed
            since the last call.
        """
        return self._telemetry_gate.poll(self.telemetry())

    def receive(self) -> "bytearray | None":
        """Poll for a complete received packet.

        Must be called every tick.  Returns decoded payload bytes when a
        complete, CRC-verified packet has been received, or ``None`` otherwise.

        Raises:
            NotImplementedError: Always — subclasses must override.
        """
        raise NotImplementedError

    @property
    def last_signal_strength(self) -> "float | None":
        """Normalised signal quality (0.0–1.0) from the last received packet.

        Returns ``None`` before any packet has been received.
        """
        return None

    @property
    def last_error_margin(self) -> "int | None":
        """Worst-case timing deviation (µs) from the last received packet.

        Returns ``None`` before any packet has been received.
        """
        return None

    @property
    def last_best_receiver(self) -> "PulseReader | None":
        """The :class:`PulseReader` that produced the best packet last tick.

        Returns ``None`` for :class:`InfraredSingleReceiver` (only one reader)
        and before any packet has been received for multi-receivers.
        """
        return None


# ---------------------------------------------------------------------------
# Source receiver — shared decoder/reader-list telemetry machinery
# ---------------------------------------------------------------------------


class InfraredSourceReceiver(InfraredReceiver):
    """Intermediate base owning the decoder/reader lists behind a receiver.

    :class:`InfraredSingleReceiver` and :class:`InfraredMultiReceiver` differ
    genuinely in how :meth:`receive` picks a packet (one reader vs. N picking
    the lowest-error-margin winner), so that stays on the concrete
    subclasses. What they share is the telemetry cross-cut: both read and
    reset walk the same *decoders* and *readers* lists, so a single receiver
    is simply the N=1 case of the same machinery.

    :meth:`telemetry` and :meth:`reset_telemetry` walk ``OWNED_TELEMETRY_FIELDS``
    declared on :class:`~hardware.shared.ir_codecs.base.InfraredDecoder`,
    :class:`PulseReader`, and :class:`InfraredReceiver` — decoder-owned
    fields are summed across ``decoders``, reader-owned fields summed across
    ``readers``, and receiver-owned fields read (and reset) directly off
    ``self``. Because every field name is walked from its declared owner,
    there is no hand-maintained field list here to drift out of sync with a
    new counter or a receiver that forgets to reset one of its sources.

    Args:
        readers: One :class:`PulseReader` per source (length 1 for a single
            receiver, N for a multi-receiver).
        decoders: One :class:`~hardware.shared.ir_codecs.base.InfraredDecoder`
            per source, matching *readers* one-to-one.
        gate: :class:`IrTransmitGate` read for self-echo suppression.
    """

    def __init__(
        self,
        readers: "list[PulseReader]",
        decoders: "list[InfraredDecoder]",
        gate: "IrTransmitGate | None" = None,
    ) -> None:
        super().__init__()
        self._readers = readers
        self._decoders = decoders
        self._gate = gate

        # Monotonic-since-boot telemetry owned by this receiver. Decoder and
        # reader counters are not copied — they are summed/reset live from
        # the lists above so the whole path reads off this one handle.
        self.pulses_seen: int = 0
        self.packets_surfaced: int = 0
        self.pulses_dropped_transmitting: int = 0

    def telemetry(self) -> IrTelemetrySnapshot:
        """Build a snapshot by walking each counter's declared owner.

        Decoder-owned fields (``packets_started``, ``packets_completed``,
        ``preamble_reject``, ``mark_reject``, ``space_reject``) are summed
        across every decoder; the reader-owned field (``buffer_full_on_poll``)
        is summed across every reader; the three receiver-owned fields are
        read off ``self``. Built entirely from keyword arguments assembled
        from each owner's declared field tuple, so the mapping cannot drift
        from ``IrTelemetrySnapshot.FIELDS`` regardless of field order.

        Returns:
            The current tick's :class:`IrTelemetrySnapshot`.
        """
        fields: dict[str, int] = {}

        for name in InfraredReceiver.OWNED_TELEMETRY_FIELDS:
            fields[name] = getattr(self, name)

        for name in InfraredDecoder.OWNED_TELEMETRY_FIELDS:
            fields[name] = sum(getattr(decoder, name) for decoder in self._decoders)

        for name in PulseReader.OWNED_TELEMETRY_FIELDS:
            fields[name] = sum(getattr(reader, name) for reader in self._readers)

        return IrTelemetrySnapshot(**fields)

    def reset_telemetry(self) -> None:
        """Zero this receiver's own counters, then every decoder and reader.

        Resetting every source that :meth:`telemetry` reads from means a
        counter can never go stale after a reset the way
        ``buffer_full_on_poll`` used to on a multi-receiver — reading and
        resetting walk the same lists, so there is nothing left to forget.
        Also rebuilds :meth:`telemetry_line`'s change-gate baseline, so the
        next call reports unconditionally.
        """
        for name in InfraredReceiver.OWNED_TELEMETRY_FIELDS:
            setattr(self, name, 0)
        for decoder in self._decoders:
            decoder.reset_telemetry()
        for reader in self._readers:
            reader.reset_telemetry()
        self._telemetry_gate = IrTelemetryGate()


# ---------------------------------------------------------------------------
# Single receiver
# ---------------------------------------------------------------------------


class InfraredSingleReceiver(InfraredSourceReceiver):
    """Polls one :class:`PulseReader` and decodes with one decoder instance.

    ``last_best_receiver`` is always ``None`` — there is only one reader, so
    there is no selection to report. The N=1 case of
    :class:`InfraredSourceReceiver` — its telemetry/reset walk a one-element
    decoder/reader list.

    Args:
        pulse_reader: Hardware port supplying pulse durations.
        decoder: :class:`~hardware.shared.ir_codecs.base.InfraredDecoder` subclass
            that processes pulses and returns a payload when a packet completes.
        gate: :class:`IrTransmitGate` read for self-echo suppression.
    """

    def __init__(
        self,
        pulse_reader: PulseReader,
        decoder: InfraredDecoder,
        gate: "IrTransmitGate | None" = None,
    ) -> None:
        super().__init__([pulse_reader], [decoder], gate)
        self._reader = pulse_reader
        self._decoder = decoder

    def receive(self) -> "bytearray | None":
        """Drain available pulses from the reader and return a packet if complete.

        With a *gate* present, pulses captured while transmitting are
        drained and discarded rather than decoded (self-echo suppression).

        Returns:
            ``bytearray`` payload on a successful decode; ``None`` otherwise.
        """
        gate = self._gate
        if gate is not None and gate.should_discard():
            self._drain_discard()
            return None

        while True:
            pulse = self._reader.read_pulse()
            if pulse is None:
                return None
            self.pulses_seen += 1
            result = self._decoder.decode(pulse)
            if result is not None:
                self.packets_surfaced += 1
                return result

    def _drain_discard(self) -> None:
        """Drain every available pulse from the reader, discarding each.

        Increments ``pulses_dropped_transmitting`` per pulse (not
        ``pulses_seen``) and resets the decoder so any in-progress decode is
        abandoned.
        """
        reader = self._reader
        while reader.read_pulse() is not None:
            self.pulses_dropped_transmitting += 1
        self._decoder.reset()

    @property
    def last_signal_strength(self) -> "float | None":
        """Signal quality forwarded from the underlying decoder."""
        return self._decoder.last_signal_strength

    @property
    def last_error_margin(self) -> "int | None":
        """Error margin forwarded from the underlying decoder."""
        return self._decoder.last_error_margin

    @property
    def last_best_receiver(self) -> "PulseReader | None":
        """Always ``None`` — a single receiver has no selection concept."""
        return None


# ---------------------------------------------------------------------------
# Multi-receiver
# ---------------------------------------------------------------------------


class InfraredMultiReceiver(InfraredSourceReceiver):
    """Polls multiple :class:`PulseReader` instances and picks the best packet.

    Each reader is paired with an independent decoder instance created by
    ``decoder_factory``.  When more than one decoder completes a packet in the
    same tick the receiver with the **lowest error margin** wins — this
    improves reliability across a wide reception area.  Multiple receivers do
    **not** derive direction.

    ``receive()`` is polled every tick and must not allocate in the hot path.
    All scratch structures are pre-allocated in ``__init__`` and reused.

    Telemetry note — **dedup, not loss**: :meth:`telemetry`'s summed
    ``packets_completed`` may exceed ``packets_surfaced`` even though nothing
    was dropped. Multiple decoders can each independently complete the same
    in-flight shot in one tick; only the lowest-error-margin winner surfaces
    from :meth:`receive`, so the rest are discarded as duplicates, not lost.
    This is unlike :class:`InfraredSingleReceiver`, where the two counters are
    always 1:1.

    Args:
        pulse_readers: Sequence of :class:`PulseReader` instances to poll.
        decoder_factory: Called once per reader at construction; must return a
            fresh :class:`~hardware.shared.ir_codecs.base.InfraredDecoder` each
            call so readers never share decode state.
        gate: :class:`IrTransmitGate` read for self-echo suppression.

    Attributes:
        last_signal_strength: Normalised quality (0.0–1.0) of the best packet
            from the last successful ``receive()``, or ``None`` before first.
        last_error_margin: Worst-case timing deviation (µs) of the winning
            packet, or ``None`` before first.
        last_best_receiver: The :class:`PulseReader` whose decoder produced
            the winning packet, or ``None`` before first.
    """

    def __init__(
        self,
        pulse_readers: "list[PulseReader]",
        decoder_factory: "Callable[[], InfraredDecoder]",
        gate: "IrTransmitGate | None" = None,
    ) -> None:
        # Freeze the reader list and create one decoder per reader
        readers = list(pulse_readers)
        decoders = [decoder_factory() for _ in readers]
        super().__init__(readers, decoders, gate)
        self._count = len(readers)

        # Pre-allocate per-receiver scratch: one slot per reader for (margin, index)
        # _scratch_margins[i] holds the error_margin from reader i when it fires
        # _scratch_fired[i] is True when reader i produced a packet this tick
        self._scratch_margins: list[int] = [0] * self._count
        self._scratch_fired: list[bool] = [False] * self._count
        self._scratch_packets: list[bytearray | None] = [None] * self._count  # type: ignore[list-item]

        # Telemetry from the last winning packet
        self._last_signal_strength: float | None = None
        self._last_error_margin: int | None = None
        self._last_best_receiver: PulseReader | None = None

    def receive(self) -> "bytearray | None":
        """Poll all readers and return the best packet this tick, or ``None``.

        With a *gate* present, pulses captured while transmitting are
        drained and discarded across every reader rather than decoded
        (self-echo suppression).

        The inner loop allocates nothing — scratch lists are cleared and
        reused each call.  The best packet is the one whose decoder reports
        the lowest ``last_error_margin``.

        Returns:
            ``bytearray`` payload from the best-signal receiver, or ``None``.
        """
        gate = self._gate
        if gate is not None and gate.should_discard():
            self._drain_discard_all()
            return None

        # Hoist scratch lists to locals for fast access (avoids repeated attr lookup)
        scratch_margins = self._scratch_margins
        scratch_fired = self._scratch_fired
        scratch_packets = self._scratch_packets
        readers = self._readers
        decoders = self._decoders
        count = self._count

        # Clear scratch — no allocation; mutate in place
        for i in range(count):
            scratch_fired[i] = False
            scratch_margins[i] = 0
            scratch_packets[i] = None

        # Drain each reader and collect any completed packets
        any_fired = False
        for i in range(count):
            reader = readers[i]
            decoder = decoders[i]
            while True:
                pulse = reader.read_pulse()
                if pulse is None:
                    break
                self.pulses_seen += 1
                packet = decoder.decode(pulse)
                if packet is not None:
                    scratch_fired[i] = True
                    scratch_margins[i] = decoder.last_error_margin
                    scratch_packets[i] = packet
                    any_fired = True
                    break  # one packet per reader per tick

        if not any_fired:
            return None

        # Pick the winner: lowest error margin among fired receivers
        best_i = -1
        best_margin = None
        for i in range(count):
            if not scratch_fired[i]:
                continue
            margin = scratch_margins[i]
            if best_margin is None or margin < best_margin:
                best_margin = margin
                best_i = i

        # Update telemetry using the winning decoder
        winning_decoder = decoders[best_i]
        self._last_error_margin = winning_decoder.last_error_margin
        self._last_signal_strength = winning_decoder.last_signal_strength
        self._last_best_receiver = readers[best_i]
        self.packets_surfaced += 1

        return scratch_packets[best_i]

    def _drain_discard_all(self) -> None:
        """Drain every available pulse from every reader, discarding each.

        Increments ``pulses_dropped_transmitting`` per pulse across all
        readers and resets every decoder so no in-progress decode survives.
        Allocates nothing — reuses the existing reader/decoder lists.
        """
        readers = self._readers
        decoders = self._decoders
        count = self._count
        dropped = 0
        for i in range(count):
            reader = readers[i]
            while reader.read_pulse() is not None:
                dropped += 1
            decoders[i].reset()
        self.pulses_dropped_transmitting += dropped

    @property
    def last_signal_strength(self) -> "float | None":
        """Normalised signal quality from the last winning packet."""
        return self._last_signal_strength

    @property
    def last_error_margin(self) -> "int | None":
        """Error margin (µs) from the last winning packet."""
        return self._last_error_margin

    @property
    def last_best_receiver(self) -> "PulseReader | None":
        """The :class:`PulseReader` that produced the best packet last tick."""
        return self._last_best_receiver

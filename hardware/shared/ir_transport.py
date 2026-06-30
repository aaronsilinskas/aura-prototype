"""Hardware-agnostic IR transport layer for the Aura platform.

Provides the ``PulseReader`` / ``PulseWriter`` port abstractions, the
``InfraredTransmitter``, and the ``InfraredSingleReceiver`` /
``InfraredMultiReceiver`` receivers built on top of the protocol codec from
``hardware.shared.ir_protocol``.

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

from hardware.shared.ir_protocol import InfraredDecoder, InfraredEncoder

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
# Transmitter
# ---------------------------------------------------------------------------


class InfraredTransmitter:
    """Encodes byte payloads and writes IR pulses via a :class:`PulseWriter`.

    Args:
        pulse_writer: Hardware port that physically transmits pulses.
        encoder: :class:`~hardware.shared.ir_protocol.InfraredEncoder` subclass
            that converts bytes to a pulse-duration array.
    """

    def __init__(self, pulse_writer: PulseWriter, encoder: InfraredEncoder) -> None:
        self._writer = pulse_writer
        self._encoder = encoder

    def send(self, data: bytes) -> None:
        """Encode *data* and transmit it via the pulse writer.

        Args:
            data: Opaque payload bytes to transmit.
        """
        pulses = self._encoder.encode(data)
        self._writer.write_pulses(pulses)


# ---------------------------------------------------------------------------
# Receiver base
# ---------------------------------------------------------------------------


class InfraredReceiver:
    """Abstract base for IR receivers.

    Subclasses implement :meth:`receive`, which must be polled every tick.
    Exposes telemetry attributes populated after each successful decode:
    ``last_signal_strength``, ``last_error_margin``, and
    ``last_best_receiver``.

    Defines the telemetry-counter contract for the whole IR receive path —
    every counter below defaults to 0 so any receiver (including test fakes)
    satisfies the contract. Concrete receivers (e.g.
    :class:`InfraredSingleReceiver`) override these to report real,
    monotonic-since-boot counts.

    Attributes:
        pulses_seen: Count of pulses drained from the reader.
        packets_surfaced: Count of decoded packets returned by :meth:`receive`.
        packets_started: Decoder packets-started count (delegated).
        packets_completed: Decoder packets-completed count (delegated).
        preamble_reject: Decoder preamble-reject count (delegated).
        mark_reject: Decoder mark-reject count (delegated).
        space_reject: Decoder space-reject count (delegated).
        buffer_full_on_poll: Reader buffer-full-on-poll count (delegated).
    """

    pulses_seen: int = 0
    packets_surfaced: int = 0
    packets_started: int = 0
    packets_completed: int = 0
    preamble_reject: int = 0
    mark_reject: int = 0
    space_reject: int = 0
    buffer_full_on_poll: int = 0

    def reset_telemetry(self) -> None:
        """Zero every counter in the IR-path telemetry contract.

        No-op on the base — receivers that track real counters (e.g.
        :class:`InfraredSingleReceiver`) override this to also reset their
        decoder and reader.
        """
        self.pulses_seen = 0
        self.packets_surfaced = 0
        self.packets_started = 0
        self.packets_completed = 0
        self.preamble_reject = 0
        self.mark_reject = 0
        self.space_reject = 0
        self.buffer_full_on_poll = 0

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
# Single receiver
# ---------------------------------------------------------------------------


class InfraredSingleReceiver(InfraredReceiver):
    """Polls one :class:`PulseReader` and decodes with one decoder instance.

    ``last_best_receiver`` is always ``None`` — there is only one reader, so
    there is no selection to report.

    Args:
        pulse_reader: Hardware port supplying pulse durations.
        decoder: :class:`~hardware.shared.ir_protocol.InfraredDecoder` subclass
            that processes pulses and returns a payload when a packet completes.
    """

    def __init__(self, pulse_reader: PulseReader, decoder: InfraredDecoder) -> None:
        self._reader = pulse_reader
        self._decoder = decoder

        # Monotonic-since-boot telemetry owned by this receiver. Decoder and
        # reader counters are not copied — they are forwarded live via the
        # properties below so the whole path reads off this one handle.
        self.pulses_seen: int = 0
        self.packets_surfaced: int = 0

    def receive(self) -> "bytearray | None":
        """Drain available pulses from the reader and return a packet if complete.

        Returns:
            ``bytearray`` payload on a successful decode; ``None`` otherwise.
        """
        while True:
            pulse = self._reader.read_pulse()
            if pulse is None:
                return None
            self.pulses_seen += 1
            result = self._decoder.decode(pulse)
            if result is not None:
                self.packets_surfaced += 1
                return result

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

    @property
    def packets_started(self) -> int:
        """Decoder packets-started count, forwarded live."""
        return self._decoder.packets_started

    @property
    def packets_completed(self) -> int:
        """Decoder packets-completed count, forwarded live."""
        return self._decoder.packets_completed

    @property
    def preamble_reject(self) -> int:
        """Decoder preamble-reject count, forwarded live."""
        return self._decoder.preamble_reject

    @property
    def mark_reject(self) -> int:
        """Decoder mark-reject count, forwarded live."""
        return self._decoder.mark_reject

    @property
    def space_reject(self) -> int:
        """Decoder space-reject count, forwarded live."""
        return self._decoder.space_reject

    @property
    def buffer_full_on_poll(self) -> int:
        """Reader buffer-full-on-poll count, forwarded live."""
        return self._reader.buffer_full_on_poll

    def reset_telemetry(self) -> None:
        """Zero the whole IR path: this receiver, its decoder, and its reader."""
        self.pulses_seen = 0
        self.packets_surfaced = 0
        self._decoder.reset_telemetry()
        self._reader.reset_telemetry()


# ---------------------------------------------------------------------------
# Multi-receiver
# ---------------------------------------------------------------------------


class InfraredMultiReceiver(InfraredReceiver):
    """Polls multiple :class:`PulseReader` instances and picks the best packet.

    Each reader is paired with an independent decoder instance created by
    ``decoder_factory``.  When more than one decoder completes a packet in the
    same tick the receiver with the **lowest error margin** wins — this
    improves reliability across a wide reception area.  Multiple receivers do
    **not** derive direction.

    ``receive()`` is polled every tick and must not allocate in the hot path.
    All scratch structures are pre-allocated in ``__init__`` and reused.

    Args:
        pulse_readers: Sequence of :class:`PulseReader` instances to poll.
        decoder_factory: Callable (no arguments) that returns a new
            :class:`~hardware.shared.ir_protocol.InfraredDecoder` instance.
            Called once per reader at construction time.

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
        decoder_factory: "object",
    ) -> None:
        # Freeze the reader list and create one decoder per reader
        self._readers = list(pulse_readers)
        self._decoders = [decoder_factory() for _ in self._readers]
        self._count = len(self._readers)

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

        The inner loop allocates nothing — scratch lists are cleared and
        reused each call.  The best packet is the one whose decoder reports
        the lowest ``last_error_margin``.

        Returns:
            ``bytearray`` payload from the best-signal receiver, or ``None``.
        """
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

        return scratch_packets[best_i]

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

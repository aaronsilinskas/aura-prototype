"""Shared base classes for IR wire-frame codecs on the Aura platform.

Provides ``InfraredEncoder`` and ``InfraredDecoder`` — the abstract base
classes every concrete codec (:mod:`hardware.shared.ir_codecs.aura`,
:mod:`hardware.shared.ir_codecs.tag`) subclasses for its telemetry/bit/pulse
machinery.

No ``pulseio`` import — safe on CPython, CircuitPython 10.x, and MicroPython.
"""

from array import array

# ---------------------------------------------------------------------------
# Abstract base classes
# ---------------------------------------------------------------------------


class InfraredEncoder:
    """Abstract base: encodes byte payloads into IR pulse sequences.

    Subclasses implement :meth:`encode` to map opaque bytes onto an
    ``array.array`` of pulse durations (µs), alternating mark/space.
    No ``pulseio`` dependency — the array is passed to the hardware layer
    by the caller.
    """

    def encode(self, data: bytes) -> array:
        """Encode *data* into a pulse-duration array.

        Args:
            data: Opaque payload bytes to transmit.

        Returns:
            ``array.array('H', …)`` of pulse durations in microseconds,
            alternating mark/space, starting with a mark.

        Raises:
            NotImplementedError: Always — subclasses must override.
        """
        raise NotImplementedError


class InfraredDecoder:
    """Abstract base: stateful IR pulse-stream decoder.

    Processes one pulse at a time via :meth:`decode`, tracks the worst-case
    timing *error margin* across the current packet, and exposes a normalised
    *signal strength* (0.0–1.0) after each successful decode.

    Args:
        error_threshold: Maximum tolerated timing deviation in µs.  Pulses
            that deviate more than this from their expected value are rejected.

    Attributes:
        last_error_margin: Worst-case timing deviation (µs) for the last
            decoded packet, or ``None`` before any packet is decoded.
        last_signal_strength: Normalised quality metric (0.0–1.0) derived
            from *last_error_margin*.  An error ≤ 30 % of the threshold
            counts as full strength (1.0).  ``None`` before first decode.
        packets_started: Monotonic-since-boot count of packets that began
            decoding (e.g. a fully matched preamble). Defaults to 0 — only
            :class:`~hardware.shared.ir_codecs.tag.TagInfraredDecoder` tracks
            this; other decoders (and fakes) satisfy the contract via this
            class-level default.
        packets_completed: Monotonic-since-boot count of successfully
            decoded packets. Defaults to 0, as above.
        preamble_reject: Monotonic-since-boot count of preamble-stage
            rejections. Defaults to 0, as above.
        mark_reject: Monotonic-since-boot count of mark-pulse rejections.
            Defaults to 0, as above.
        space_reject: Monotonic-since-boot count of space-pulse rejections.
            Defaults to 0, as above.
    """

    # The IR receive-path telemetry counters this class owns — the read
    # source ``InfraredSourceReceiver.telemetry()`` sums across every decoder
    # and the reset source ``reset_telemetry()`` zeroes on every decoder. An
    # explicit tuple, not derived from ``__slots__``, which also carries this
    # class's seven private decode-state slots.
    OWNED_TELEMETRY_FIELDS = (
        "packets_started",
        "packets_completed",
        "preamble_reject",
        "mark_reject",
        "space_reject",
    )

    __slots__ = (
        "_decoder_state",
        "_error_threshold",
        "_last_error_margin",
        "_max_error_margin",
        "_received_bit_index",
        "_received_byte",
        "_received_data",
        "mark_reject",
        "packets_completed",
        "packets_started",
        "preamble_reject",
        "space_reject",
    )

    def __init__(self, error_threshold: int) -> None:
        self._error_threshold = error_threshold

        # State machine position
        self._decoder_state: int = 0
        # Byte accumulator — cleared in place on reset to avoid per-packet allocation
        self._received_data: bytearray = bytearray()
        # Bit-writer state (MSB-first: starts at bit 7)
        self._received_bit_index: int = 7
        self._received_byte: int = 0

        # Timing-error tracking for the current packet
        self._max_error_margin: int = 0
        # Timing-error result from the last completed packet (None = never decoded)
        self._last_error_margin: int | None = None

        # Monotonic-since-boot telemetry counters
        self.packets_started: int = 0
        self.packets_completed: int = 0
        self.preamble_reject: int = 0
        self.mark_reject: int = 0
        self.space_reject: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def decode(self, pulse: int) -> bytearray | None:
        """Process a single pulse duration and return decoded data if complete.

        Args:
            pulse: Pulse duration in microseconds.

        Returns:
            ``bytearray`` payload if a complete, valid packet was decoded;
            ``None`` if more pulses are needed, an error occurred, or the
            packet was rejected.

        Raises:
            NotImplementedError: Always — subclasses must override.
        """
        raise NotImplementedError

    @property
    def last_error_margin(self) -> int | None:
        """Worst-case timing deviation (µs) from the last decoded packet.

        Returns ``None`` before any packet has been successfully decoded.
        """
        return self._last_error_margin

    @property
    def last_signal_strength(self) -> float | None:
        """Normalised signal quality (0.0–1.0) from the last decoded packet.

        An error margin of 0 or ≤ 30 % of the error threshold yields 1.0.
        Returns ``None`` before any packet has been decoded.
        """
        if self._last_error_margin is None:
            return None
        if self._last_error_margin == 0:
            return 1.0
        error_ratio = self._last_error_margin / self._error_threshold
        return min(1.0, 1.3 - error_ratio)

    def reset_telemetry(self) -> None:
        """Zero the shared telemetry counters.

        The base implementation serves every decoder, including
        ``TagInfraredDecoder``: they all increment these same base-declared
        counters, so none needs to override this."""
        self.packets_started = 0
        self.packets_completed = 0
        self.preamble_reject = 0
        self.mark_reject = 0
        self.space_reject = 0

    def reset(self, error_margin: int | None = None) -> None:
        """Return the decoder to idle, discarding any in-progress decode.

        Decode state only — telemetry is untouched (see :meth:`reset_telemetry`).
        """
        self._decoder_state = 0
        self._received_data = bytearray()  # MicroPython does not support clear() on bytearray
        self._received_bit_index = 7
        self._received_byte = 0
        self._max_error_margin = 0
        self._last_error_margin = error_margin

    # ------------------------------------------------------------------
    # Helpers for subclasses (not part of the public API)
    # ------------------------------------------------------------------

    def _check_pulse(
        self, received: int, expected: int, error_threshold: int | None = None
    ) -> bool:
        """Return ``True`` if *received* is within the error threshold of *expected*.

        Tracks the worst-case deviation in ``_max_error_margin``. Defaults to
        ``self._error_threshold``; pass *error_threshold* to override it.
        """
        if error_threshold is None:
            error_threshold = self._error_threshold
        margin = abs(received - expected)
        if margin < error_threshold:
            if margin > self._max_error_margin:
                self._max_error_margin = margin
            return True
        return False

    def _write_bit(self, bit: int) -> None:
        """Accumulate *bit* (0 or 1) MSB-first into the current byte."""
        if bit:
            self._received_byte |= 1 << self._received_bit_index
        self._received_bit_index -= 1
        if self._received_bit_index < 0:
            self._received_data.append(self._received_byte)
            self._received_byte = 0
            self._received_bit_index = 7

"""Behaviour-driven tests for the shared IR codec base classes."""

import pytest

from hardware.shared.ir_codecs.base import InfraredDecoder, InfraredEncoder
from hardware.shared.ir_codecs.tag import (
    TAG_PREAMBLE,
    TagInfraredDecoder,
    TagInfraredEncoder,
)

_IR_ERROR_THRESHOLD = 250  # µs — arbitrary threshold for exercising the base class directly


def _feed_pulses(decoder: InfraredDecoder, pulses) -> bytearray | None:
    """Feed every pulse in *pulses* to *decoder*; return the first decoded payload."""
    for pulse in pulses:
        result = decoder.decode(pulse)
        if result is not None:
            return result
    return None


# ---------------------------------------------------------------------------
# Base-class contracts
# ---------------------------------------------------------------------------


def test_encoder_base_rejects_call_without_subclass():
    enc = InfraredEncoder()
    with pytest.raises(NotImplementedError):
        enc.encode(b"\x01")


def test_decoder_base_rejects_call_without_subclass():
    dec = InfraredDecoder(_IR_ERROR_THRESHOLD)
    with pytest.raises(NotImplementedError):
        dec.decode(500)


# ---------------------------------------------------------------------------
# reset()
# ---------------------------------------------------------------------------


def test_reset_does_not_zero_telemetry_counters():
    # A concrete decoder is needed to exercise telemetry increments — the
    # base class only declares the counters; TagInfraredDecoder is the one
    # that mutates preamble_reject on a malformed preamble.
    decoder = TagInfraredDecoder()
    bad_preamble = list(TAG_PREAMBLE)
    bad_preamble[1] = 4000  # invalid but below the inter-frame gap threshold
    _feed_pulses(decoder, bad_preamble)
    assert decoder.preamble_reject == 1

    decoder.reset()

    assert decoder.preamble_reject == 1


def test_reset_returns_decoder_to_idle_so_the_next_signal_decodes_cleanly():
    # reset()'s core job is to discard an in-progress partial decode and return
    # to idle. Drive a partial packet (preamble matched, one data bit already
    # accumulated but the packet unfinished), reset, then feed a fresh clean
    # packet: it must decode to its own value, proving the abandoned partial was
    # discarded and neither blocked nor corrupted the next decode.
    encoder = TagInfraredEncoder()
    decoder = TagInfraredDecoder()

    # Preamble plus the first three data-bit pulses — enough to leave the
    # bit-writer mid-byte, short of the finalising pulse.
    partial = list(encoder.encode(bytearray([0x7F])))[: len(TAG_PREAMBLE) + 3]
    _feed_pulses(decoder, partial)

    decoder.reset()

    fresh_value = 0x2A  # independent literal — unrelated to the abandoned partial
    result = _feed_pulses(decoder, encoder.encode(bytearray([fresh_value])))

    assert result == bytearray([fresh_value])

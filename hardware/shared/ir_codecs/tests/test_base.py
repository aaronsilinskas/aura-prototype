"""Behaviour-driven tests for the shared IR codec base classes."""

import pytest

from hardware.shared.ir_codecs.base import InfraredDecoder, InfraredEncoder
from hardware.shared.ir_codecs.tag import TAG_PREAMBLE, TagInfraredDecoder

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

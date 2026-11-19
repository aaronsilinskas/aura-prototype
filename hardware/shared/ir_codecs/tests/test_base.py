"""Behaviour-driven tests for the shared IR codec base classes."""

import pytest

from hardware.shared.ir_codecs.aura import AuraInfraredDecoder, AuraInfraredEncoder
from hardware.shared.ir_codecs.base import InfraredDecoder, InfraredEncoder
from hardware.shared.ir_codecs.tag import (
    TAG_PREAMBLE,
    TagInfraredDecoder,
    TagInfraredEncoder,
)

_IR_ERROR_THRESHOLD = 250  # µs — arbitrary threshold for exercising the base class directly

_NUDGE = 100  # µs — inside both codecs' tolerance, so the frame still decodes

# Each codec with the index of its first data-bit space, the pulse nudged to
# give a completed packet a known, non-zero error margin.
_CODECS = [
    pytest.param(AuraInfraredEncoder, AuraInfraredDecoder, 3, id="aura"),
    pytest.param(TagInfraredEncoder, TagInfraredDecoder, len(TAG_PREAMBLE) + 1, id="tag"),
]


def _feed_pulses(decoder: InfraredDecoder, pulses) -> bytearray | None:
    """Feed every pulse in *pulses* to *decoder*; return the first decoded payload."""
    for pulse in pulses:
        result = decoder.decode(pulse)
        if result is not None:
            return result
    return None


def test_encoder_base_rejects_call_without_subclass():
    enc = InfraredEncoder()
    with pytest.raises(NotImplementedError):
        enc.encode(b"\x01")


def test_decoder_base_rejects_call_without_subclass():
    dec = InfraredDecoder(_IR_ERROR_THRESHOLD)
    with pytest.raises(NotImplementedError):
        dec.decode(500)


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


def _nudged_frame(encoder_class, space_index: int, payload: int) -> list[int]:
    pulses = list(encoder_class().encode(bytearray([payload])))
    pulses[space_index] += _NUDGE
    return pulses


@pytest.mark.parametrize(("encoder_class", "decoder_class", "space_index"), _CODECS)
def test_completing_a_packet_records_its_error_margin(encoder_class, decoder_class, space_index):
    decoder = decoder_class()

    _feed_pulses(decoder, _nudged_frame(encoder_class, space_index, 0x2A))

    assert decoder.last_error_margin == _NUDGE


@pytest.mark.parametrize(("encoder_class", "decoder_class", "space_index"), _CODECS)
def test_reset_after_a_completed_packet_keeps_its_error_margin_and_signal_strength(
    encoder_class, decoder_class, space_index
):
    decoder = decoder_class()
    _feed_pulses(decoder, _nudged_frame(encoder_class, space_index, 0x2A))
    strength = decoder.last_signal_strength

    decoder.reset()

    assert decoder.last_error_margin == _NUDGE
    assert decoder.last_signal_strength == strength


@pytest.mark.parametrize(("encoder_class", "decoder_class", "space_index"), _CODECS)
def test_a_rejected_frame_after_a_completed_packet_keeps_its_error_margin(
    encoder_class, decoder_class, space_index
):
    decoder = decoder_class()
    _feed_pulses(decoder, _nudged_frame(encoder_class, space_index, 0x2A))
    broken = list(encoder_class().encode(bytearray([0x15])))
    broken[space_index] = 3500  # no data space in either codec, and below the tag gap

    assert _feed_pulses(decoder, broken) is None

    assert decoder.last_error_margin == _NUDGE

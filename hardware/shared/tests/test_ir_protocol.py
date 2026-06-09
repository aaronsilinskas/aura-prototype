"""Behaviour-driven tests for the Aura IR protocol codec.

Covers:
- Round-trip encode→decode for several payload lengths
- CRC mismatch rejection (no data emitted)
- Short/malformed frame rejection
- Signal-strength heuristic boundaries
- Base-class contracts (InfraredEncoder, InfraredDecoder)
"""

import pytest

from hardware.shared.ir_protocol import (
    IR_MARK_ONE,
    IR_MARK_ZERO,
    IR_SPACE_ONE,
    IR_SPACE_ZERO,
    AuraInfraredDecoder,
    AuraInfraredEncoder,
    InfraredDecoder,
    InfraredEncoder,
)

# ---------------------------------------------------------------------------
# Local copies of wire-frame constants used by tests to corrupt pulses.
# Redefined here so tests do not silently pass when the source constants change.
# ---------------------------------------------------------------------------

_IR_HEADER_MARK = 4000
_IR_HEADER_SPACE = 3000
_IR_LEAD_OUT = 5000
_IR_UNIT = 500
_IR_ERROR_THRESHOLD = _IR_UNIT // 2  # 250 µs — tolerance window


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _feed_pulses(decoder: AuraInfraredDecoder, pulses) -> "bytearray | None":
    """Feed every pulse in *pulses* to *decoder*; return the first decoded payload."""
    for pulse in pulses:
        result = decoder.decode(pulse)
        if result is not None:
            return result
    return None


def _encode_decode(payload: bytes) -> "bytearray | None":
    encoder = AuraInfraredEncoder()
    decoder = AuraInfraredDecoder()
    return _feed_pulses(decoder, encoder.encode(payload))


def _corrupt_last_crc_space(pulses: list) -> list:
    """Return a copy of *pulses* with the last CRC bit space flipped.

    Layout: lead-out at [-1], last CRC bit space at [-2].  Flipping the space
    changes the decoded CRC byte without disturbing the frame structure.
    """
    corrupted = list(pulses)
    idx = len(corrupted) - 2
    corrupted[idx] = IR_SPACE_ONE if corrupted[idx] == IR_SPACE_ZERO else IR_SPACE_ZERO
    return corrupted


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
# Round-trip: several payload lengths and boundary values
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        bytes([0xAB]),
        bytes([0x01, 0xFF]),
        bytes([0x10, 0x20, 0x30, 0x40]),
        bytes(range(8)),
        bytes([0x00, 0x00, 0x00]),  # all-zero CRC boundary
        bytes([0xFF, 0xFF, 0xFF]),  # all-one CRC boundary
        bytes([0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80]),  # bit-walk
    ],
)
def test_decoded_payload_matches_encoded_input(payload: bytes):
    assert _encode_decode(payload) == bytearray(payload)


# ---------------------------------------------------------------------------
# Encoder: wire-frame structure
# ---------------------------------------------------------------------------


def test_encoder_frame_begins_with_header_mark():
    pulses = AuraInfraredEncoder().encode(b"\x00")
    assert pulses[0] == _IR_HEADER_MARK


def test_encoder_frame_second_slot_is_header_space():
    pulses = AuraInfraredEncoder().encode(b"\x00")
    assert pulses[1] == _IR_HEADER_SPACE


def test_encoder_frame_ends_with_lead_out():
    pulses = AuraInfraredEncoder().encode(b"\x00")
    assert pulses[-1] == _IR_LEAD_OUT


def test_encoder_frame_length_covers_header_payload_crc_and_lead_out():
    # header(2) + (payload + CRC) bytes * 8 bits * 2 slots + lead_out(1)
    payload = bytes([0xAB, 0xCD])
    pulses = AuraInfraredEncoder().encode(payload)
    expected_len = 2 + (len(payload) + 1) * 8 * 2 + 1
    assert len(pulses) == expected_len


def test_encoder_encodes_zero_bit_as_short_space():
    # 0x00 — all bits are zero; first data bit starts at index 2.
    pulses = AuraInfraredEncoder().encode(b"\x00")
    assert pulses[2] == IR_MARK_ZERO
    assert pulses[3] == IR_SPACE_ZERO


def test_encoder_encodes_one_bit_as_long_space():
    # 0x80 — MSB is 1; first data bit starts at index 2.
    pulses = AuraInfraredEncoder().encode(b"\x80")
    assert pulses[2] == IR_MARK_ONE
    assert pulses[3] == IR_SPACE_ONE


# ---------------------------------------------------------------------------
# CRC rejection
# ---------------------------------------------------------------------------


def test_corrupted_crc_byte_produces_no_output():
    encoder = AuraInfraredEncoder()
    corrupted = _corrupt_last_crc_space(list(encoder.encode(b"\xab\xcd")))
    result = _feed_pulses(AuraInfraredDecoder(), corrupted)
    assert result is None


def test_corrupted_packet_is_discarded_and_next_valid_packet_decodes():
    encoder = AuraInfraredEncoder()
    decoder = AuraInfraredDecoder()

    corrupted = _corrupt_last_crc_space(list(encoder.encode(b"\xab")))
    rejected = _feed_pulses(decoder, corrupted)
    assert rejected is None

    payload = b"\xcd"
    result = _feed_pulses(decoder, encoder.encode(payload))
    assert result == bytearray(payload)


# ---------------------------------------------------------------------------
# Malformed / short frame rejection
# ---------------------------------------------------------------------------


def test_frame_with_only_header_and_lead_out_is_rejected():
    """Header followed immediately by lead-out — no data bytes — is rejected."""
    encoder = AuraInfraredEncoder()
    full = list(encoder.encode(b"\x00"))
    short = [full[0], full[1], full[-1]]  # header mark + space + lead-out only

    result = _feed_pulses(AuraInfraredDecoder(), short)
    assert result is None


def test_out_of_range_pulse_mid_frame_causes_frame_to_be_dropped():
    """An unrecognised pulse during data reception drops the in-progress frame."""
    encoder = AuraInfraredEncoder()
    pulses = list(encoder.encode(b"\xab"))
    mid = len(pulses) // 2
    pulses.insert(mid, 9999)

    result = _feed_pulses(AuraInfraredDecoder(), pulses)
    assert result is None


def test_invalid_header_space_causes_frame_to_be_dropped():
    """A garbage header space resets the decoder — no output for that frame."""
    encoder = AuraInfraredEncoder()
    pulses = list(encoder.encode(b"\x01"))
    pulses[1] = 1234  # replace valid header space with garbage

    result = _feed_pulses(AuraInfraredDecoder(), pulses)
    assert result is None


# ---------------------------------------------------------------------------
# Signal strength heuristic
# ---------------------------------------------------------------------------


def test_signal_strength_is_none_before_first_packet():
    assert AuraInfraredDecoder().last_signal_strength is None


def test_signal_strength_is_full_for_perfect_timing():
    encoder = AuraInfraredEncoder()
    decoder = AuraInfraredDecoder()
    _feed_pulses(decoder, encoder.encode(b"\x42"))
    assert decoder.last_signal_strength == 1.0


def test_signal_strength_is_full_when_error_is_at_thirty_percent_of_threshold():
    encoder = AuraInfraredEncoder()
    decoder = AuraInfraredDecoder()

    pulses = list(encoder.encode(b"\xab"))
    nudge = int(_IR_ERROR_THRESHOLD * 0.30)  # exactly at the 30 % boundary
    pulses[2] += nudge

    _feed_pulses(decoder, pulses)
    assert decoder.last_signal_strength == 1.0


def test_signal_strength_is_partial_when_error_exceeds_thirty_percent_of_threshold():
    encoder = AuraInfraredEncoder()
    decoder = AuraInfraredDecoder()

    pulses = list(encoder.encode(b"\xff"))
    nudge = int(_IR_ERROR_THRESHOLD * 0.60)  # 60 % — above the full-strength boundary
    pulses[2] += nudge

    _feed_pulses(decoder, pulses)
    strength = decoder.last_signal_strength
    assert strength is not None
    assert 0.0 < strength < 1.0


def test_signal_strength_below_half_at_worst_accepted_error():
    """An error margin just under the rejection threshold yields low signal strength."""
    encoder = AuraInfraredEncoder()
    decoder = AuraInfraredDecoder()

    pulses = list(encoder.encode(b"\x00"))
    nudge = _IR_ERROR_THRESHOLD - 1  # 249 µs — largest error still accepted
    pulses[2] += nudge

    _feed_pulses(decoder, pulses)
    strength = decoder.last_signal_strength
    assert strength is not None
    assert 0.0 <= strength < 0.4


# ---------------------------------------------------------------------------
# last_error_margin
# ---------------------------------------------------------------------------


def test_error_margin_is_none_before_first_packet():
    assert AuraInfraredDecoder().last_error_margin is None


def test_error_margin_is_zero_for_perfect_timing():
    encoder = AuraInfraredEncoder()
    decoder = AuraInfraredDecoder()
    _feed_pulses(decoder, encoder.encode(b"\x00"))
    assert decoder.last_error_margin == 0


def test_error_margin_reflects_worst_case_deviation_in_frame():
    encoder = AuraInfraredEncoder()
    decoder = AuraInfraredDecoder()

    pulses = list(encoder.encode(b"\xab\xcd"))
    nudge = 50  # µs — shift a data bit space slightly
    pulses[3] += nudge  # index 3 = first data bit space

    _feed_pulses(decoder, pulses)
    assert decoder.last_error_margin == nudge


def test_error_margin_is_replaced_by_subsequent_packet():
    encoder = AuraInfraredEncoder()
    decoder = AuraInfraredDecoder()

    _feed_pulses(decoder, encoder.encode(b"\x00"))
    assert decoder.last_error_margin == 0

    pulses = list(encoder.encode(b"\xff"))
    nudge = 40
    pulses[3] += nudge  # first data bit space
    _feed_pulses(decoder, pulses)

    assert decoder.last_error_margin == nudge


# ---------------------------------------------------------------------------
# Decoder: noise tolerance
# ---------------------------------------------------------------------------


def test_decoder_discards_unrecognised_pulses_before_header_mark():
    encoder = AuraInfraredEncoder()
    decoder = AuraInfraredDecoder()

    noise = [100, 200, 50, 300]
    result = _feed_pulses(decoder, noise + list(encoder.encode(b"\xab")))
    assert result == bytearray(b"\xab")

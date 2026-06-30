"""Behaviour-driven tests for the infrared tag IR protocol codec.

Covers:
- TagData value object (slots, no dataclasses)
- encode_tag_data / decode_tag_data round-trip and validation
- TagInfraredEncoder / TagInfraredDecoder wire round-trip
- last_error_margin / last_signal_strength after a successful decode
"""

import pytest

from hardware.shared.tag_protocol import (
    TAG_DAMAGE_BITS,
    TAG_ERROR_MARGIN,
    TAG_GAP_THRESHOLD,
    TAG_PLAYER_BITS,
    TAG_PREAMBLE,
    TAG_PREAMBLE_ERROR_MARGIN,
    TAG_SPACE_ONE,
    TAG_SPACE_ZERO,
    TAG_TEAM_BITS,
    TagData,
    TagInfraredDecoder,
    TagInfraredEncoder,
    decode_tag_data,
    encode_tag_data,
)

# ---------------------------------------------------------------------------
# TagData value object
# ---------------------------------------------------------------------------


def test_tag_data_stores_team_player_and_damage():
    tag = TagData(team=2, player=5, damage=3)

    assert tag.team == 2
    assert tag.player == 5
    assert tag.damage == 3


def test_tag_data_uses_slots_with_no_instance_dict():
    tag = TagData(team=0, player=1, damage=1)

    assert not hasattr(tag, "__dict__")


# ---------------------------------------------------------------------------
# encode_tag_data / decode_tag_data
# ---------------------------------------------------------------------------


def test_minimum_tag_data_encodes_to_zero_byte():
    assert encode_tag_data(TagData(team=0, player=1, damage=1)) == bytearray([0x00])


@pytest.mark.parametrize("team", range(4))
@pytest.mark.parametrize("player", range(1, 9))
@pytest.mark.parametrize("damage", range(1, 5))
def test_encode_decode_round_trips_for_all_valid_field_values(team, player, damage):
    tag = TagData(team=team, player=player, damage=damage)

    decoded = decode_tag_data(encode_tag_data(tag))

    assert decoded.team == team
    assert decoded.player == player
    assert decoded.damage == damage


@pytest.mark.parametrize(
    "team, player, damage",
    [
        (-1, 1, 1),
        (4, 1, 1),
        (0, 0, 1),
        (0, 9, 1),
        (0, 1, 0),
        (0, 1, 5),
    ],
)
def test_encode_raises_for_out_of_range_fields(team, player, damage):
    tag = TagData(team=team, player=player, damage=damage)

    with pytest.raises(ValueError):
        encode_tag_data(tag)


def test_decode_raises_for_empty_data():
    with pytest.raises(ValueError):
        decode_tag_data(b"")


# ---------------------------------------------------------------------------
# Wire round-trip
# ---------------------------------------------------------------------------


def _encode_decode_byte(byte: int) -> bytearray | None:
    encoder = TagInfraredEncoder()
    decoder = TagInfraredDecoder()

    # The decoder finalises inline on the 17th pulse (the space pulse that
    # completes the final data bit) — no trailing pulse is needed.
    pulses = encoder.encode(bytearray([byte]))
    for pulse in pulses:
        result = decoder.decode(pulse)
        if result is not None:
            return result
    return None


@pytest.mark.parametrize("byte", [0x00, 0x01, 0x7F, 0x55, 0x2A])
def test_wire_round_trip_recovers_original_byte(byte):
    assert _encode_decode_byte(byte) == bytearray([byte])


def test_isolated_packet_decodes_on_its_17th_pulse_with_no_trailing_pulse():
    encoder = TagInfraredEncoder()
    decoder = TagInfraredDecoder()

    pulses = encoder.encode(bytearray([0x55]))
    assert len(pulses) == 17

    result = None
    for pulse in pulses:
        result = decoder.decode(pulse)

    assert result == bytearray([0x55])


def test_back_to_back_burst_decodes_both_shots_without_dropping_the_second_preamble():
    encoder = TagInfraredEncoder()
    decoder = TagInfraredDecoder()

    pulses = [*encoder.encode(bytearray([0x55])), *encoder.encode(bytearray([0x2A]))]

    results = []
    for pulse in pulses:
        outcome = decoder.decode(pulse)
        if outcome is not None:
            results.append(outcome)

    assert results == [bytearray([0x55]), bytearray([0x2A])]


def test_encoder_frame_starts_with_preamble():
    pulses = TagInfraredEncoder().encode(bytearray([0x00]))

    assert list(pulses[: len(TAG_PREAMBLE)]) == TAG_PREAMBLE


def test_encoder_frame_length_covers_preamble_and_data_bits():
    data_bits = TAG_TEAM_BITS + TAG_PLAYER_BITS + TAG_DAMAGE_BITS
    pulses = TagInfraredEncoder().encode(bytearray([0x00]))

    assert len(pulses) == len(TAG_PREAMBLE) + data_bits * 2


def test_encoder_encodes_one_bit_as_long_space():
    # 0x40 -> shifted left by 1 -> 0x80 -> first data bit is 1
    pulses = TagInfraredEncoder().encode(bytearray([0x40]))

    first_bit_space_index = len(TAG_PREAMBLE) + 1
    assert pulses[first_bit_space_index] == TAG_SPACE_ONE


def test_encoder_encodes_zero_bit_as_short_space():
    pulses = TagInfraredEncoder().encode(bytearray([0x00]))

    first_bit_space_index = len(TAG_PREAMBLE) + 1
    assert pulses[first_bit_space_index] == TAG_SPACE_ZERO


# ---------------------------------------------------------------------------
# Telemetry: last_error_margin / last_signal_strength
# ---------------------------------------------------------------------------


def test_successful_decode_exposes_error_margin_and_signal_strength():
    encoder = TagInfraredEncoder()
    decoder = TagInfraredDecoder()

    pulses = encoder.encode(bytearray([0x55]))
    for pulse in pulses:
        decoder.decode(pulse)

    assert decoder.last_error_margin is not None
    assert decoder.last_signal_strength is not None


def test_perfect_timing_yields_zero_error_margin_and_full_signal_strength():
    encoder = TagInfraredEncoder()
    decoder = TagInfraredDecoder()

    pulses = encoder.encode(bytearray([0x2A]))
    for pulse in pulses:
        decoder.decode(pulse)

    assert decoder.last_error_margin == 0
    assert decoder.last_signal_strength == 1.0


# ---------------------------------------------------------------------------
# Decoder: noise tolerance and frame rejection
# ---------------------------------------------------------------------------


def test_decoder_discards_unrecognised_pulses_before_preamble():
    encoder = TagInfraredEncoder()
    decoder = TagInfraredDecoder()

    noise = [100, 200, 50]
    pulses = [*noise, *encoder.encode(bytearray([0x33]))]

    result = None
    for pulse in pulses:
        outcome = decoder.decode(pulse)
        if outcome is not None:
            result = outcome
    assert result == bytearray([0x33])


# ---------------------------------------------------------------------------
# Decoder: per-stage error margin (preamble looser than data bits)
# ---------------------------------------------------------------------------

_BETWEEN_MARGINS = (TAG_ERROR_MARGIN + TAG_PREAMBLE_ERROR_MARGIN) // 2


def test_preamble_pulse_within_widened_margin_still_decodes():
    decoder = TagInfraredDecoder()

    decoder.decode(TAG_PREAMBLE[0] + _BETWEEN_MARGINS)
    decoder.decode(TAG_PREAMBLE[1])
    decoder.decode(TAG_PREAMBLE[2])

    assert decoder.packets_started == 1
    assert decoder.preamble_reject == 0


def test_data_bit_pulse_outside_narrow_margin_still_rejects_despite_wider_preamble_margin():
    encoder = TagInfraredEncoder()
    decoder = TagInfraredDecoder()

    pulses = list(encoder.encode(bytearray([0x10])))[: len(TAG_PREAMBLE) + 1]
    pulses[-1] += _BETWEEN_MARGINS

    for pulse in pulses:
        decoder.decode(pulse)

    assert decoder.mark_reject == 1


# ---------------------------------------------------------------------------
# Decoder: inter-frame gap termination
# ---------------------------------------------------------------------------


def test_gap_pulse_mid_preamble_returns_none_instead_of_decoding_as_data():
    decoder = TagInfraredDecoder()

    decoder.decode(TAG_PREAMBLE[0])
    result = decoder.decode(TAG_GAP_THRESHOLD)

    assert result is None


def test_gap_pulse_mid_packet_is_not_counted_as_a_mark_or_space_reject():
    encoder = TagInfraredEncoder()
    decoder = TagInfraredDecoder()

    partial = list(encoder.encode(bytearray([0x55])))[: len(TAG_PREAMBLE) + 2]
    for pulse in partial:
        decoder.decode(pulse)
    decoder.decode(TAG_GAP_THRESHOLD)

    assert decoder.mark_reject == 0
    assert decoder.space_reject == 0
    assert decoder.preamble_reject == 0


def test_gap_pulse_does_not_cause_the_following_pulse_to_be_discarded():
    decoder = TagInfraredDecoder()

    decoder.decode(TAG_PREAMBLE[0])
    decoder.decode(TAG_GAP_THRESHOLD)
    encoder = TagInfraredEncoder()
    pulses = encoder.encode(bytearray([0x2A]))
    result = None
    for pulse in pulses:
        outcome = decoder.decode(pulse)
        if outcome is not None:
            result = outcome

    assert result == bytearray([0x2A])


def test_corrupt_partial_packet_then_gap_then_clean_packet_yields_clean_payload():
    encoder = TagInfraredEncoder()
    decoder = TagInfraredDecoder()

    # Simulates an overlapping/interrupted transmission: preamble matches,
    # then a corrupted mark pulse collides mid-decode.
    corrupt = list(encoder.encode(bytearray([0x10])))[: len(TAG_PREAMBLE) + 1]
    corrupt[-1] = 4000  # invalid mark pulse
    for pulse in corrupt:
        decoder.decode(pulse)
    decoder.decode(TAG_GAP_THRESHOLD)
    clean = encoder.encode(bytearray([0x55]))
    result = None
    for pulse in clean:
        outcome = decoder.decode(pulse)
        if outcome is not None:
            result = outcome

    assert result == bytearray([0x55])


def test_invalid_preamble_pulse_resets_decoder():
    encoder = TagInfraredEncoder()
    decoder = TagInfraredDecoder()

    pulses = list(encoder.encode(bytearray([0x10])))
    pulses[1] = 4000  # corrupt the second preamble pulse

    result = None
    for pulse in pulses:
        outcome = decoder.decode(pulse)
        if outcome is not None:
            result = outcome
    assert result is None


# ---------------------------------------------------------------------------
# Telemetry: per-stage reject/completion counters
# ---------------------------------------------------------------------------


def test_invalid_preamble_pulse_increments_preamble_reject():
    decoder = TagInfraredDecoder()

    pulses = list(TAG_PREAMBLE)
    pulses[1] = 4000  # corrupt the second preamble pulse

    for pulse in pulses:
        decoder.decode(pulse)

    assert decoder.preamble_reject == 1
    assert decoder.mark_reject == 0
    assert decoder.space_reject == 0


def test_invalid_mark_pulse_after_preamble_increments_mark_reject():
    encoder = TagInfraredEncoder()
    decoder = TagInfraredDecoder()

    # Stop right after the corrupted pulse — feeding further pulses would be
    # reinterpreted as preamble noise once the decoder resets to idle.
    pulses = list(encoder.encode(bytearray([0x10])))[: len(TAG_PREAMBLE) + 1]
    pulses[-1] = 4000  # corrupt the first data-bit mark

    for pulse in pulses:
        decoder.decode(pulse)

    assert decoder.mark_reject == 1
    assert decoder.preamble_reject == 0
    assert decoder.space_reject == 0


def test_invalid_space_pulse_increments_space_reject():
    encoder = TagInfraredEncoder()
    decoder = TagInfraredDecoder()

    # Stop right after the corrupted pulse — feeding further pulses would be
    # reinterpreted as preamble noise once the decoder resets to idle.
    pulses = list(encoder.encode(bytearray([0x10])))[: len(TAG_PREAMBLE) + 2]
    pulses[-1] = 4000  # corrupt the first data-bit space

    for pulse in pulses:
        decoder.decode(pulse)

    assert decoder.space_reject == 1
    assert decoder.preamble_reject == 0
    assert decoder.mark_reject == 0


def test_full_preamble_match_increments_packets_started():
    decoder = TagInfraredDecoder()

    for pulse in TAG_PREAMBLE:
        decoder.decode(pulse)

    assert decoder.packets_started == 1
    assert decoder.packets_completed == 0


def test_completed_packet_increments_packets_completed():
    encoder = TagInfraredEncoder()
    decoder = TagInfraredDecoder()

    pulses = encoder.encode(bytearray([0x55]))
    for pulse in pulses:
        decoder.decode(pulse)

    assert decoder.packets_started == 1
    assert decoder.packets_completed == 1


def test_packets_started_counts_every_preamble_match_not_just_completions():
    encoder = TagInfraredEncoder()
    decoder = TagInfraredDecoder()

    # First packet: preamble matches but mark is corrupted — never completes.
    aborted = list(encoder.encode(bytearray([0x10])))[: len(TAG_PREAMBLE) + 1]
    aborted[-1] = 4000
    for pulse in aborted:
        decoder.decode(pulse)

    # Second packet: completes normally.
    completed = encoder.encode(bytearray([0x2A]))
    for pulse in completed:
        decoder.decode(pulse)

    assert decoder.packets_started == 2
    assert decoder.packets_completed == 1


def test_reset_telemetry_zeroes_all_decoder_counters():
    encoder = TagInfraredEncoder()
    decoder = TagInfraredDecoder()

    pulses = encoder.encode(bytearray([0x55]))
    for pulse in pulses:
        decoder.decode(pulse)
    bad_preamble = list(TAG_PREAMBLE)
    bad_preamble[1] = 4000
    for pulse in bad_preamble:
        decoder.decode(pulse)

    decoder.reset_telemetry()

    assert decoder.packets_started == 0
    assert decoder.packets_completed == 0
    assert decoder.preamble_reject == 0
    assert decoder.mark_reject == 0
    assert decoder.space_reject == 0

"""Transmit-side IR behaviour, observed through InfraredTransceiver.

Every transceiver is built from fake pulse readers and writers. The tests
assert only on what a caller sees: the pulses each emitter's writer wrote,
what ``busy`` reports, and what ``update`` receives next.
"""

from array import array

import pytest

from engine.network import AREA_OF_EFFECT, CONE, LINE
from hardware.shared.ir_codecs.aura import AuraInfraredDecoder, AuraInfraredEncoder
from hardware.shared.ir_codecs.tag import TagInfraredDecoder, TagInfraredEncoder
from hardware.shared.ir_transceiver import InfraredTransceiver
from hardware.shared.ir_transport import PulseWriter
from hardware.shared.tests.ir_fakes import (
    EmitterPulseWriter,
    EmitterWriterFactory,
    ReplayingPulseReader,
    aura_pulses,
    tag_pulses,
)


def _build(
    *emitters: str, blocking: bool = True, echo: bool = False
) -> tuple[InfraredTransceiver, dict[str, EmitterPulseWriter], ReplayingPulseReader]:
    """A transceiver over one reader and a fake writer per *emitters* (``LINE`` if none).

    With *echo*, every write also lands on the reader as self-echo.
    """
    reader = ReplayingPulseReader()
    factory = EmitterWriterFactory(blocking=blocking, echo_to=[reader] if echo else None)
    pins = {emitter: emitter for emitter in emitters or (LINE,)}
    transceiver = InfraredTransceiver([reader], pins, factory)
    return transceiver, factory.writers, reader


# ---------------------------------------------------------------------------
# send() — each emitter writes its own encoded pulses
# ---------------------------------------------------------------------------


def test_send_writes_each_payload_only_on_its_own_emitters_writer() -> None:
    transceiver, writers, _ = _build(LINE, CONE, AREA_OF_EFFECT)

    transceiver.send(b"\x01", LINE)
    transceiver.send(b"\x02", CONE)

    assert writers[LINE].calls == [aura_pulses(b"\x01")]
    assert writers[CONE].calls == [aura_pulses(b"\x02")]
    assert writers[AREA_OF_EFFECT].calls == []


def test_every_send_to_an_idle_writer_is_written_once_in_order() -> None:
    transceiver, writers, _ = _build()

    transceiver.send(b"\x01", LINE)
    transceiver.send(b"\x02", LINE)

    assert writers[LINE].calls == [aura_pulses(b"\x01"), aura_pulses(b"\x02")]


# ---------------------------------------------------------------------------
# Queuing behind a busy writer
# ---------------------------------------------------------------------------


def test_a_send_while_the_writer_is_busy_writes_nothing_yet() -> None:
    transceiver, writers, _ = _build(blocking=False)
    transceiver.send(b"\x01", LINE)

    transceiver.send(b"\x02", LINE)
    transceiver.update(0.0)

    assert writers[LINE].calls == [aura_pulses(b"\x01")]


def test_sends_queued_behind_a_busy_writer_are_written_oldest_first_one_per_finished_write() -> (
    None
):
    transceiver, writers, _ = _build(blocking=False)
    writer = writers[LINE]
    transceiver.send(b"\x01", LINE)
    transceiver.send(b"\x02", LINE)
    transceiver.send(b"\x03", LINE)

    writer.finish()
    transceiver.update(0.0)
    transceiver.update(0.0)  # \x02 still in flight: \x03 must wait
    assert writer.calls == [aura_pulses(b"\x01"), aura_pulses(b"\x02")]

    writer.finish()
    transceiver.update(0.0)
    writer.finish()
    transceiver.update(0.0)  # queue empty: nothing is written twice
    assert writer.calls == [aura_pulses(b"\x01"), aura_pulses(b"\x02"), aura_pulses(b"\x03")]


class _CountingEncoder(AuraInfraredEncoder):
    """An Aura encoder counting every ``encode`` across all its instances."""

    encodes = 0

    def encode(self, data: bytes) -> "array[int]":
        _CountingEncoder.encodes += 1
        return super().encode(data)


def test_a_queued_payload_is_encoded_once_when_its_write_starts_not_every_tick() -> None:
    _CountingEncoder.encodes = 0
    transceiver, writers, _ = _build(blocking=False)
    transceiver.apply_codec(_CountingEncoder, AuraInfraredDecoder)
    transceiver.send(b"\x01", LINE)
    transceiver.send(b"\x02", LINE)

    transceiver.update(0.0)
    transceiver.update(0.0)
    assert _CountingEncoder.encodes == 1

    writers[LINE].finish()
    transceiver.update(0.0)
    transceiver.update(0.0)
    assert _CountingEncoder.encodes == 2


class _RejectingEncoder(AuraInfraredEncoder):
    """An Aura encoder that cannot encode the payload ``b"\\x02"``."""

    def encode(self, data: bytes) -> "array[int]":
        if data == b"\x02":
            raise ValueError("unencodable payload")
        return super().encode(data)


def test_a_queued_payload_failing_to_encode_raises_from_update_and_the_rest_still_send() -> None:
    transceiver, writers, _ = _build(blocking=False)
    transceiver.apply_codec(_RejectingEncoder, AuraInfraredDecoder)
    writer = writers[LINE]
    transceiver.send(b"\x01", LINE)
    transceiver.send(b"\x02", LINE)  # queued, so its encode error cannot surface here
    transceiver.send(b"\x03", LINE)

    writer.finish()
    with pytest.raises(ValueError):
        transceiver.update(0.0)
    transceiver.update(0.0)

    assert writer.calls == [aura_pulses(b"\x01"), aura_pulses(b"\x03")]


def test_update_starts_queued_sends_on_every_emitter_even_with_no_receiver() -> None:
    factory = EmitterWriterFactory(blocking=False)
    transceiver = InfraredTransceiver([], {LINE: "GP1", CONE: "GP2"}, factory)
    for emitter in (LINE, CONE):
        transceiver.send(b"\x01", emitter)
        transceiver.send(b"\x02", emitter)
        factory.writers[emitter].finish()

    transceiver.update(0.0)

    for emitter in (LINE, CONE):
        assert factory.writers[emitter].calls == [aura_pulses(b"\x01"), aura_pulses(b"\x02")]


# ---------------------------------------------------------------------------
# busy() — reports one emitter and pumps only that emitter
# ---------------------------------------------------------------------------


def test_busy_is_false_for_an_emitter_that_has_sent_nothing() -> None:
    transceiver, _, _ = _build(blocking=False)

    assert transceiver.busy(LINE) is False


def test_busy_reports_a_write_in_flight_until_the_writer_finishes() -> None:
    transceiver, writers, _ = _build(blocking=False)
    transceiver.send(b"\x01", LINE)

    assert transceiver.busy(LINE) is True
    assert transceiver.busy(LINE) is True

    writers[LINE].finish()
    assert transceiver.busy(LINE) is False


def test_busy_starts_the_emitters_queued_send_and_reports_it_in_flight() -> None:
    transceiver, writers, _ = _build(blocking=False)
    transceiver.send(b"\x01", LINE)
    transceiver.send(b"\x02", LINE)
    writers[LINE].finish()

    assert transceiver.busy(LINE) is True
    assert writers[LINE].calls == [aura_pulses(b"\x01"), aura_pulses(b"\x02")]


def test_busy_starts_queued_sends_only_on_the_emitter_it_names() -> None:
    transceiver, writers, _ = _build(LINE, CONE, blocking=False)
    for emitter in (LINE, CONE):
        transceiver.send(b"\x01", emitter)
        transceiver.send(b"\x02", emitter)
        writers[emitter].finish()

    transceiver.busy(LINE)

    assert writers[LINE].calls == [aura_pulses(b"\x01"), aura_pulses(b"\x02")]
    assert writers[CONE].calls == [aura_pulses(b"\x01")]


# ---------------------------------------------------------------------------
# Gate release ordering within a tick
# ---------------------------------------------------------------------------


def test_a_write_finished_before_update_releases_the_gate_so_the_next_frame_decodes() -> None:
    transceiver, writers, reader = _build(blocking=False)
    transceiver.send(b"\x01", LINE)
    transceiver.update(0.0)

    writers[LINE].finish()
    transceiver.update(0.0)  # pumps first: releases the gate, then the one falling-edge drain
    reader.load(aura_pulses(b"\x2a"))
    transceiver.update(0.0)

    assert transceiver.received == bytearray(b"\x2a")


def test_frames_are_discarded_until_every_emitters_write_has_finished() -> None:
    transceiver, writers, reader = _build(LINE, CONE, blocking=False)
    transceiver.send(b"\x01", LINE)
    transceiver.send(b"\x01", CONE)
    writers[LINE].finish()
    transceiver.update(0.0)

    reader.load(aura_pulses(b"\x2a"))
    transceiver.update(0.0)  # CONE still lit
    assert transceiver.received is None

    writers[CONE].finish()
    transceiver.update(0.0)
    reader.load(aura_pulses(b"\x2b"))
    transceiver.update(0.0)
    assert transceiver.received == bytearray(b"\x2b")


def test_a_frame_is_received_after_two_back_to_back_sends_finish_with_no_update_between() -> None:
    transceiver, writers, reader = _build(blocking=False)
    transceiver.send(b"\x01", LINE)
    writers[LINE].finish()
    transceiver.send(b"\x02", LINE)
    writers[LINE].finish()
    transceiver.update(0.0)  # pumps first: releases the gate, then the one falling-edge drain

    reader.load(aura_pulses(b"\x2a"))
    transceiver.update(0.0)

    assert transceiver.received == bytearray(b"\x2a")


def test_a_writer_failing_mid_send_raises_and_does_not_leave_reception_blocked() -> None:
    class _FailingWriter(PulseWriter):
        def write_pulses(self, durations: "array[int]") -> None:
            raise RuntimeError("hardware fault")

        def is_busy(self) -> bool:
            return False

    reader = ReplayingPulseReader()
    transceiver = InfraredTransceiver(
        [reader], {LINE: "GP1"}, lambda emitter, pin: (_FailingWriter(), "fake")
    )

    with pytest.raises(RuntimeError):
        transceiver.send(b"\x01", LINE)
    transceiver.update(0.0)
    reader.load(aura_pulses(b"\x2a"))
    transceiver.update(0.0)

    assert transceiver.received == bytearray(b"\x2a")


# ---------------------------------------------------------------------------
# apply_codec() — later sends use the new wire-frame
# ---------------------------------------------------------------------------


def test_apply_codec_encodes_later_sends_in_the_new_wire_frame_on_every_emitter() -> None:
    transceiver, writers, _ = _build(LINE, CONE)

    transceiver.apply_codec(TagInfraredEncoder, TagInfraredDecoder)
    transceiver.send(b"\x10", LINE)
    transceiver.send(b"\x20", CONE)

    assert writers[LINE].calls == [tag_pulses(b"\x10")]
    assert writers[CONE].calls == [tag_pulses(b"\x20")]


def test_apply_codec_encodes_a_send_already_queued_in_the_new_wire_frame() -> None:
    transceiver, writers, _ = _build(blocking=False)
    transceiver.send(b"\x01", LINE)
    transceiver.send(b"\x10", LINE)

    transceiver.apply_codec(TagInfraredEncoder, TagInfraredDecoder)
    writers[LINE].finish()
    transceiver.update(0.0)

    assert writers[LINE].calls == [aura_pulses(b"\x01"), tag_pulses(b"\x10")]


# ---------------------------------------------------------------------------
# Self-echo — drained but never decoded while transmitting, and once more after
# ---------------------------------------------------------------------------


def test_a_sends_self_echo_is_never_received_and_the_next_frame_is() -> None:
    transceiver, _, reader = _build(echo=True)

    transceiver.send(b"\x01", LINE)
    transceiver.update(0.0)
    assert transceiver.received is None

    reader.load(aura_pulses(b"\x2a"))
    transceiver.update(0.0)
    assert transceiver.received == bytearray(b"\x2a")


def test_every_frame_arriving_while_a_write_is_in_flight_is_discarded() -> None:
    """A real shot overlapping the self-echo is indistinguishable from it at
    the pulse level, so both are dropped."""
    transceiver, _, reader = _build(blocking=False, echo=True)
    transceiver.send(b"\x01", LINE)

    reader.load(aura_pulses(b"\x2a"))
    transceiver.update(0.0)
    assert transceiver.received is None

    reader.load(aura_pulses(b"\x2b"))
    transceiver.update(0.0)
    assert transceiver.received is None


def test_pulses_waiting_when_the_write_finishes_are_discarded_once_more_on_the_falling_edge() -> (
    None
):
    transceiver, writers, reader = _build(blocking=False)
    transceiver.send(b"\x01", LINE)
    transceiver.update(0.0)

    writers[LINE].finish()
    reader.load(aura_pulses(b"\x2a"))  # echo tail still buffered in the reader
    transceiver.update(0.0)
    assert transceiver.received is None

    reader.load(aura_pulses(b"\x2b"))
    transceiver.update(0.0)
    assert transceiver.received == bytearray(b"\x2b")


def test_back_to_back_sends_discard_frames_while_either_is_lit_and_on_the_falling_edge() -> None:
    transceiver, writers, reader = _build(blocking=False, echo=True)
    transceiver.send(b"\x01", LINE)
    reader.load(aura_pulses(b"\x29"))
    transceiver.update(0.0)  # first write still lit
    assert transceiver.received is None

    writers[LINE].finish()
    transceiver.send(b"\x02", LINE)  # no update since the first write finished

    reader.load(aura_pulses(b"\x2a"))
    transceiver.update(0.0)  # second write still lit
    assert transceiver.received is None

    writers[LINE].finish()
    reader.load(aura_pulses(b"\x2b"))  # echo tail still buffered in the reader
    transceiver.update(0.0)
    assert transceiver.received is None


def test_a_frame_partly_decoded_when_the_device_sends_is_abandoned() -> None:
    transceiver, _, reader = _build()
    frame = aura_pulses(b"\x2a")
    reader.load(frame[:6])
    transceiver.update(0.0)

    transceiver.send(b"\x01", LINE)
    reader.load(frame[6:])
    transceiver.update(0.0)
    assert transceiver.received is None

    reader.load(aura_pulses(b"\x2b"))
    transceiver.update(0.0)
    assert transceiver.received == bytearray(b"\x2b")

"""Behaviour-driven tests for InfraredTransceiver (hardware/shared/ir_transceiver.py)."""

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


def _transceiver_over(
    readers: list[ReplayingPulseReader] | None = None,
    writers: dict[str, PulseWriter] | None = None,
) -> InfraredTransceiver:
    """A transceiver built over *readers*, wiring each emitter in *writers* to that writer."""
    wired = writers or {}
    return InfraredTransceiver(
        list(readers or []),
        {emitter: emitter for emitter in wired},
        lambda emitter, _pin: (wired[emitter], "fake"),
    )


_ALL_PINS = {LINE: "GP1", CONE: "GP2", AREA_OF_EFFECT: "GP3"}


# ---------------------------------------------------------------------------
# Construction — wires itself from pulse readers, emitter pins and a writer factory
# ---------------------------------------------------------------------------


def test_constructor_calls_the_factory_once_per_emitter_in_ir_emitters_order_with_its_pin() -> None:
    factory = EmitterWriterFactory()
    pins = {AREA_OF_EFFECT: object(), LINE: object(), CONE: object()}

    transceiver = InfraredTransceiver([ReplayingPulseReader()], pins, factory)

    assert factory.calls == [
        (LINE, pins[LINE]),
        (CONE, pins[CONE]),
        (AREA_OF_EFFECT, pins[AREA_OF_EFFECT]),
    ]
    assert transceiver.emitters == (LINE, CONE, AREA_OF_EFFECT)


def test_constructor_reports_the_writer_kind_the_factory_produced() -> None:
    transceiver = InfraredTransceiver(
        [ReplayingPulseReader()], {LINE: "GP1"}, EmitterWriterFactory(kind="pio")
    )

    assert transceiver.writer_kind == "pio"


def test_constructor_with_no_emitter_pins_wires_no_emitter_and_reports_no_writer_kind() -> None:
    factory = EmitterWriterFactory()

    transceiver = InfraredTransceiver([ReplayingPulseReader()], {}, factory)

    assert factory.calls == []
    assert transceiver.emitters == ()
    assert transceiver.writer_kind is None


@pytest.mark.parametrize("emitter", [LINE, CONE, AREA_OF_EFFECT])
def test_send_writes_aura_pulses_only_on_the_writer_built_for_that_emitter(
    emitter,
) -> None:
    factory = EmitterWriterFactory()
    transceiver = InfraredTransceiver([ReplayingPulseReader()], _ALL_PINS, factory)

    transceiver.send(b"\x2a", emitter)

    assert {e: w.calls for e, w in factory.writers.items()} == {
        e: [aura_pulses(b"\x2a")] if e == emitter else [] for e in _ALL_PINS
    }


def test_constructor_does_not_wire_an_emitter_missing_from_the_pins() -> None:
    transceiver = InfraredTransceiver(
        [ReplayingPulseReader()], {LINE: "GP1"}, EmitterWriterFactory()
    )

    assert transceiver.emitters == (LINE,)
    with pytest.raises(ValueError):
        transceiver.send(b"\x2a", CONE)


def test_constructor_with_no_readers_wires_no_receiver() -> None:
    transceiver = InfraredTransceiver([], {LINE: "GP1"}, EmitterWriterFactory())

    transceiver.update(0.0)

    assert transceiver.receives is False
    assert transceiver.received is None


@pytest.mark.parametrize("reader_count", [1, 3])
def test_a_new_transceiver_receives_an_aura_shot_landing_on_its_readers(reader_count) -> None:
    readers = [ReplayingPulseReader(aura_pulses(b"\x2a")) for _ in range(reader_count)]
    transceiver = InfraredTransceiver(list(readers), {}, EmitterWriterFactory())

    transceiver.update(0.0)

    assert transceiver.receives is True
    assert transceiver.received == bytearray(b"\x2a")
    assert transceiver.codec == (AuraInfraredEncoder, AuraInfraredDecoder)


@pytest.mark.parametrize("emitter", [LINE, CONE, AREA_OF_EFFECT])
def test_no_reader_receives_the_self_echo_of_a_send_on_any_emitter(
    emitter,
) -> None:
    readers = [ReplayingPulseReader(), ReplayingPulseReader()]
    transceiver = InfraredTransceiver(
        list(readers), _ALL_PINS, EmitterWriterFactory(echo_to=readers)
    )

    transceiver.send(b"\x2a", emitter)
    transceiver.update(0.0)

    assert transceiver.received is None


# ---------------------------------------------------------------------------
# send() — raises for an emitter that isn't wired
# ---------------------------------------------------------------------------


def test_send_raises_with_no_emitter_wired() -> None:
    transceiver = _transceiver_over()

    with pytest.raises(ValueError):
        transceiver.send(b"x", LINE)


def test_transceiver_does_not_expose_transmitters_as_a_public_collection() -> None:
    transceiver = _transceiver_over(writers={LINE: EmitterPulseWriter()})

    assert not hasattr(transceiver, "transmitters")


# ---------------------------------------------------------------------------
# busy() — reports and pumps one emitter
# ---------------------------------------------------------------------------


def test_busy_reports_idle_for_a_blocking_writer() -> None:
    transceiver = _transceiver_over(writers={LINE: EmitterPulseWriter()})

    transceiver.send(b"\xab", LINE)

    assert transceiver.busy(LINE) is False


def test_busy_raises_for_unwired_emitter() -> None:
    transceiver = _transceiver_over(writers={LINE: EmitterPulseWriter()})

    with pytest.raises(ValueError):
        transceiver.busy(CONE)


# ---------------------------------------------------------------------------
# update() — pumps every transmitter, then receives
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("reader_count", [0, 1])
def test_update_starts_every_emitters_queued_send_once_its_writer_finishes(
    reader_count,
) -> None:
    writers = {LINE: EmitterPulseWriter(blocking=False), CONE: EmitterPulseWriter(blocking=False)}
    transceiver = _transceiver_over(
        [ReplayingPulseReader() for _ in range(reader_count)], dict(writers)
    )
    for emitter, writer in writers.items():
        transceiver.send(b"\x01", emitter)
        transceiver.send(b"\x02", emitter)  # queued behind the write in flight
        writer.finish()

    transceiver.update(0.0)

    assert {e: w.calls for e, w in writers.items()} == {
        e: [aura_pulses(b"\x01"), aura_pulses(b"\x02")] for e in writers
    }


def test_update_with_nothing_wired_leaves_received_none() -> None:
    transceiver = _transceiver_over()

    transceiver.update(0.0)  # must not raise

    assert transceiver.received is None


# ---------------------------------------------------------------------------
# received — set only on a decoding tick
# ---------------------------------------------------------------------------


def test_received_is_none_when_the_pulses_decode_nothing() -> None:
    transceiver = _transceiver_over([ReplayingPulseReader([100, 200])])

    transceiver.update(0.0)

    assert transceiver.received is None


# ---------------------------------------------------------------------------
# apply_codec()
# ---------------------------------------------------------------------------


def test_apply_codec_makes_every_emitter_send_in_the_new_wire_frame() -> None:
    writers = {LINE: EmitterPulseWriter(), CONE: EmitterPulseWriter()}
    transceiver = _transceiver_over([ReplayingPulseReader()], dict(writers))

    transceiver.apply_codec(TagInfraredEncoder, TagInfraredDecoder)
    transceiver.send(b"\x10", LINE)
    transceiver.send(b"\x10", CONE)

    expected = tag_pulses(b"\x10")
    assert {e: w.calls for e, w in writers.items()} == {LINE: [expected], CONE: [expected]}


def test_apply_codec_makes_the_readers_decode_the_new_wire_frame() -> None:
    """A Tag frame only decodes once the Tag decoder is installed."""
    payload = bytearray([0x10])
    transceiver = _transceiver_over([ReplayingPulseReader(tag_pulses(payload))])

    transceiver.apply_codec(TagInfraredEncoder, TagInfraredDecoder)
    transceiver.update(0.0)

    assert transceiver.received == payload


def test_apply_codec_with_no_receiver_wired_still_changes_what_is_sent() -> None:
    writer = EmitterPulseWriter()
    transceiver = _transceiver_over(writers={LINE: writer})

    transceiver.apply_codec(TagInfraredEncoder, TagInfraredDecoder)  # must not raise
    transceiver.send(b"\x10", LINE)

    assert writer.calls == [tag_pulses(b"\x10")]


def test_apply_codec_is_a_safe_noop_with_nothing_wired() -> None:
    transceiver = _transceiver_over()

    transceiver.apply_codec(TagInfraredEncoder, TagInfraredDecoder)  # must not raise


# ---------------------------------------------------------------------------
# codec — the installed class pair, read back
# ---------------------------------------------------------------------------


def test_codec_is_the_aura_pair_before_any_codec_is_applied() -> None:
    transceiver = _transceiver_over()

    assert transceiver.codec == (AuraInfraredEncoder, AuraInfraredDecoder)


def test_codec_reads_back_the_class_pair_apply_codec_took() -> None:
    transceiver = _transceiver_over()

    transceiver.apply_codec(TagInfraredEncoder, TagInfraredDecoder)

    assert transceiver.codec == (TagInfraredEncoder, TagInfraredDecoder)


def test_codec_cannot_be_assigned() -> None:
    transceiver = _transceiver_over()

    with pytest.raises(AttributeError):
        transceiver.codec = (TagInfraredEncoder, TagInfraredDecoder)  # type: ignore[misc]  # proves it is read-only


# ---------------------------------------------------------------------------
# telemetry_line() — every receive-path stage reports
# ---------------------------------------------------------------------------


def test_telemetry_line_reports_a_decoded_frame_through_every_stage() -> None:
    """Uses the Tag codec because its decoder counts started and completed packets."""
    pulses = tag_pulses(b"\x10")
    transceiver = _transceiver_over([ReplayingPulseReader(pulses)])
    transceiver.apply_codec(TagInfraredEncoder, TagInfraredDecoder)

    transceiver.update(0.0)

    assert transceiver.telemetry_line() == (
        f"ir: pulses_seen={len(pulses)} buffer_full_on_poll=0 packets_started=1"
        " preamble_reject=0 mark_reject=0 space_reject=0 packets_completed=1"
        " packets_surfaced=1 pulses_dropped_transmitting=0"
    )

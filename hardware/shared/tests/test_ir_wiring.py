"""Tests for the board-free IR wiring the device builder and the Simulated device share."""

import pytest

from engine.network import AREA_OF_EFFECT, CONE, LINE
from hardware.shared.ir_codecs.aura import AuraInfraredEncoder
from hardware.shared.ir_transport import PulseReader, PulseWriter
from hardware.shared.ir_wiring import wire_ir


class _FakeReader(PulseReader):
    def __init__(self) -> None:
        self.pulses: list[int] = []

    def read_pulse(self) -> int | None:
        return self.pulses.pop(0) if self.pulses else None


class _FakeWriter(PulseWriter):
    """A blocking writer that records each write and, like a lit emitter, lights *echo_to*."""

    def __init__(self, echo_to: list[_FakeReader]) -> None:
        self.writes: list[list[int]] = []
        self._echo_to = echo_to

    def write_pulses(self, durations) -> None:
        self.writes.append(list(durations))
        for reader in self._echo_to:
            reader.pulses.extend(durations)

    def is_busy(self) -> bool:
        return False


class _WriterFactory:
    """Builds a :class:`_FakeWriter` per emitter, recording each ``(emitter, pin)`` call."""

    def __init__(self, kind: str = "fake", echo_to: list[_FakeReader] | None = None) -> None:
        self.kind = kind
        self.calls: list[tuple[str, object]] = []
        self.writers: dict[str, _FakeWriter] = {}
        self._echo_to = echo_to or []

    def __call__(self, emitter: str, pin: object) -> tuple[PulseWriter, str]:
        self.calls.append((emitter, pin))
        writer = _FakeWriter(self._echo_to)
        self.writers[emitter] = writer
        return writer, self.kind


def test_a_send_reaches_the_writer_built_for_that_emitter_in_the_aura_wire_frame():
    factory = _WriterFactory()
    transceiver, _kind = wire_ir([_FakeReader()], {LINE: "GP1", CONE: "GP2"}, factory)

    transceiver.send(b"\x2a", CONE)

    assert factory.writers[LINE].writes == []
    assert factory.writers[CONE].writes == [list(AuraInfraredEncoder().encode(b"\x2a"))]


def test_emitters_are_built_in_ir_emitters_order_with_their_key_and_pin_whatever_the_config_order():
    factory = _WriterFactory()

    wire_ir([_FakeReader()], {AREA_OF_EFFECT: "GP3", LINE: "GP1", CONE: "GP2"}, factory)

    assert factory.calls == [(LINE, "GP1"), (CONE, "GP2"), (AREA_OF_EFFECT, "GP3")]


def test_an_emitter_missing_from_the_pins_is_not_wired():
    transceiver, _kind = wire_ir([_FakeReader()], {LINE: "GP1"}, _WriterFactory())

    with pytest.raises(ValueError):
        transceiver.send(b"\x2a", CONE)


def test_the_writer_kind_is_what_the_factory_reported():
    _transceiver, kind = wire_ir([_FakeReader()], {LINE: "GP1"}, _WriterFactory(kind="pio"))

    assert kind == "pio"


def test_there_is_no_writer_kind_when_no_emitter_is_wired():
    _transceiver, kind = wire_ir([_FakeReader()], {}, _WriterFactory())

    assert kind is None


@pytest.mark.parametrize("reader_count", [1, 3])
def test_the_receiver_decodes_an_aura_shot_landing_on_its_readers(reader_count):
    readers = [_FakeReader() for _ in range(reader_count)]
    transceiver, _kind = wire_ir(readers, {}, _WriterFactory())
    for reader in readers:
        reader.pulses.extend(AuraInfraredEncoder().encode(b"\x2a"))

    transceiver.update()

    assert transceiver.received == bytearray(b"\x2a")


def test_the_receiver_reads_every_reader_not_just_the_first():
    readers = [_FakeReader(), _FakeReader()]
    transceiver, _kind = wire_ir(readers, {}, _WriterFactory())
    readers[1].pulses.extend(AuraInfraredEncoder().encode(b"\x2a"))

    transceiver.update()

    assert transceiver.received == bytearray(b"\x2a")


@pytest.mark.parametrize("emitter", [LINE, CONE, AREA_OF_EFFECT])
def test_every_emitter_shares_the_gate_so_the_device_never_hears_itself(emitter):
    reader = _FakeReader()
    factory = _WriterFactory(echo_to=[reader])
    transceiver, _kind = wire_ir(
        [reader], {LINE: "GP1", CONE: "GP2", AREA_OF_EFFECT: "GP3"}, factory
    )

    transceiver.send(b"\x2a", emitter)
    transceiver.update()

    assert transceiver.received is None

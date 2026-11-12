"""Hardware-free fakes for the infrared pulse readers and writers, plus the
wire-frame encoders and telemetry parser the IR tests share."""

from __future__ import annotations

from array import array

from hardware.shared.ir_codecs.aura import AuraInfraredEncoder
from hardware.shared.ir_codecs.tag import TagInfraredEncoder
from hardware.shared.ir_transceiver import InfraredTransceiver
from hardware.shared.ir_transport import PulseReader, PulseWriter


def aura_pulses(payload: bytes | bytearray) -> list[int]:
    """*payload* encoded in the Aura wire-frame."""
    return list(AuraInfraredEncoder().encode(bytes(payload)))


def tag_pulses(payload: bytes | bytearray) -> list[int]:
    """*payload* encoded in the Tag wire-frame."""
    return list(TagInfraredEncoder().encode(bytes(payload)))


def telemetry_counters(transceiver: InfraredTransceiver) -> dict[str, int]:
    """Parse the transceiver's telemetry line into ``{counter: value}``.

    Only valid on a call that reports — the first call, or one after a change.
    """
    line = transceiver.telemetry_line()
    assert line is not None
    return {name: int(value) for name, value in (f.split("=") for f in line.split()[1:])}


class ReplayingPulseReader(PulseReader):
    """Replays pulses the test loads, one per ``read_pulse()``, then ``None``."""

    def __init__(self, pulses: list[int] | array[int] | None = None) -> None:
        self._queue: list[int] = list(pulses) if pulses is not None else []

    def load(self, pulses: list[int] | array[int]) -> None:
        """Queue *pulses* behind anything not yet read."""
        self._queue.extend(pulses)

    def read_pulse(self) -> int | None:
        if self._queue:
            return self._queue.pop(0)
        return None


class EmitterPulseWriter(PulseWriter):
    """A writer for one emitter that records each written pulse sequence in :attr:`calls`.

    Blocking by default, like the ``PulseOutWriter``. A non-blocking writer
    stays busy after each write until the test calls :meth:`finish`, like a
    DMA-backed writer awaiting the hardware's completion signal. Each write
    also lands its pulses on *echo_to*'s readers, like a lit emitter's
    self-echo.
    """

    def __init__(
        self, blocking: bool = True, echo_to: list[ReplayingPulseReader] | None = None
    ) -> None:
        self.calls: list[list[int]] = []
        self._blocking = blocking
        self._busy = False
        self._echo_to = echo_to or []

    def write_pulses(self, durations: array[int]) -> None:
        self.calls.append(list(durations))
        self._busy = not self._blocking
        for reader in self._echo_to:
            reader.load(durations)

    def is_busy(self) -> bool:
        return self._busy

    def finish(self) -> None:
        """Signal that the in-flight write has completed."""
        self._busy = False


class EmitterWriterFactory:
    """A writer factory for ``InfraredTransceiver`` that keeps each emitter's
    :class:`EmitterPulseWriter` in :attr:`writers`, records each
    ``(emitter, pin)`` call in :attr:`calls`, and reports *kind*."""

    def __init__(
        self,
        blocking: bool = True,
        echo_to: list[ReplayingPulseReader] | None = None,
        kind: str = "fake",
    ) -> None:
        self.writers: dict[str, EmitterPulseWriter] = {}
        self.calls: list[tuple[str, object]] = []
        self._blocking = blocking
        self._echo_to = echo_to or []
        self._kind = kind

    def __call__(self, emitter: str, pin: object) -> tuple[PulseWriter, str]:
        self.calls.append((emitter, pin))
        writer = EmitterPulseWriter(self._blocking, self._echo_to)
        self.writers[emitter] = writer
        return writer, self._kind

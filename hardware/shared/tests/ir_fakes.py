"""Hardware-free fakes for the infrared pulse readers and writers."""

from __future__ import annotations

from array import array

from hardware.shared.ir_codecs.base import InfraredEncoder
from hardware.shared.ir_transport import InfraredTransmitter, PulseReader, PulseWriter


class RecordingPulseWriter(PulseWriter):
    """Captures written pulse sequences without touching hardware.

    ``is_busy()`` always reports ``False`` — matches the blocking
    ``PulseOutWriter``'s externally-observable behaviour.
    """

    def __init__(self) -> None:
        self.calls: list[list[int]] = []

    def write_pulses(self, durations: array[int]) -> None:
        self.calls.append(list(durations))

    def is_busy(self) -> bool:
        return False


class StubEncoder(InfraredEncoder):
    """Minimal encoder that converts each byte to a single pulse duration."""

    def encode(self, data: bytes) -> array[int]:
        return array("H", list(data))


def make_transmitter() -> tuple[InfraredTransmitter, RecordingPulseWriter]:
    """A transmitter over a ``StubEncoder``, and the writer recording what it sends."""
    writer = RecordingPulseWriter()
    tx = InfraredTransmitter(writer, StubEncoder())
    return tx, writer


class ReplayingPulseReader(PulseReader):
    """Replays pulses the test loads, one per ``read_pulse()``, then ``None``."""

    def __init__(self) -> None:
        self._queue: list[int] = []

    def load(self, pulses: list[int] | array[int]) -> None:
        """Queue *pulses* behind anything not yet read."""
        self._queue.extend(pulses)

    def read_pulse(self) -> int | None:
        if self._queue:
            return self._queue.pop(0)
        return None


class EmitterPulseWriter(RecordingPulseWriter):
    """A recording writer for one emitter, built by :class:`EmitterWriterFactory`.

    Blocking by default. A non-blocking writer stays busy after each write
    until the test calls :meth:`finish`, like a DMA-backed writer awaiting
    the hardware's completion signal. Each write also lands its pulses on
    *echo_to*'s readers, like a lit emitter's self-echo.
    """

    def __init__(self, blocking: bool, echo_to: list[ReplayingPulseReader]) -> None:
        super().__init__()
        self._blocking = blocking
        self._busy = False
        self._echo_to = echo_to

    def write_pulses(self, durations: array[int]) -> None:
        super().write_pulses(durations)
        self._busy = not self._blocking
        for reader in self._echo_to:
            reader.load(durations)

    def is_busy(self) -> bool:
        return self._busy

    def finish(self) -> None:
        """Signal that the in-flight write has completed."""
        self._busy = False


class EmitterWriterFactory:
    """A writer factory for ``InfraredTransceiver.build`` that keeps each
    emitter's :class:`EmitterPulseWriter` in :attr:`writers`."""

    def __init__(
        self,
        blocking: bool = True,
        echo_to: list[ReplayingPulseReader] | None = None,
    ) -> None:
        self.writers: dict[str, EmitterPulseWriter] = {}
        self._blocking = blocking
        self._echo_to = echo_to or []

    def __call__(self, emitter: str, pin: object) -> tuple[PulseWriter, str]:
        writer = EmitterPulseWriter(self._blocking, self._echo_to)
        self.writers[emitter] = writer
        return writer, "fake"

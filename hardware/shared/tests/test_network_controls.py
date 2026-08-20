import pytest

from engine.engine import GameEngine
from engine.network import CONE, LINE
from engine.state import EffectControls, NetworkControls, SceneControls
from hardware.shared.ir_transceiver import InfraredTransceiver
from hardware.shared.ir_transport import InfraredTransmitter, IrTransmitGate, PulseWriter
from hardware.shared.network_controls import HardwareNetworkControls
from hardware.shared.radio_transport import RadioTransport

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _RecordingPulseWriter(PulseWriter):
    """Captures written pulse sequences without touching hardware.

    ``is_busy()`` always reports ``False`` — matches the blocking
    ``PulseOutWriter``'s externally-observable behaviour.
    """

    def __init__(self) -> None:
        self.calls: list[list[int]] = []

    def write_pulses(self, durations: list[int]) -> None:
        self.calls.append(list(durations))

    def is_busy(self) -> bool:
        return False


class _StubEncoder:
    """Minimal encoder that converts each byte to a single-item pulse list."""

    def encode(self, data: bytes) -> list[int]:
        return list(data)


def _make_transmitter() -> tuple[InfraredTransmitter, _RecordingPulseWriter]:
    writer = _RecordingPulseWriter()
    tx = InfraredTransmitter(writer, _StubEncoder())
    return tx, writer


def _make_transceiver(**transmitters: InfraredTransmitter) -> InfraredTransceiver:
    return InfraredTransceiver(transmitters, None, IrTransmitGate())


# ---------------------------------------------------------------------------
# HardwareNetworkControls — send_ir delegates to the wired transceiver
# ---------------------------------------------------------------------------


def test_hardware_network_controls_send_ir_dispatches_correct_data() -> None:
    tx, writer = _make_transmitter()
    controls = HardwareNetworkControls(_make_transceiver(**{CONE: tx}))

    controls.send_ir(b"\xab\xcd", CONE)

    assert writer.calls[0] == [0xAB, 0xCD]


def test_hardware_network_controls_send_ir_hides_writer_completion_state() -> None:
    """send_ir is honest fire-and-forget -- the writer-type distinction
    (blocking vs. DMA/PIO) stays below this seam, owned by
    InfraredTransmitter, and never leaks upward as a bool."""
    tx, _ = _make_transmitter()
    controls = HardwareNetworkControls(_make_transceiver(**{LINE: tx}))

    assert controls.send_ir(b"\x01", LINE) is None


def test_send_ir_through_declared_network_controls_type_hides_writer_completion_state() -> None:
    """Guards the rule-facing call shape: a rule holds `state.network_controls`
    typed as `NetworkControls`, never `HardwareNetworkControls` -- calling
    `send_ir` through that declared type is honest fire-and-forget."""
    tx, writer = _make_transmitter()
    controls: NetworkControls = HardwareNetworkControls(_make_transceiver(**{LINE: tx}))

    result = controls.send_ir(b"\x01", LINE)

    assert result is None
    assert writer.calls == [[0x01]]


def test_hardware_network_controls_send_ir_routes_to_correct_transmitter() -> None:
    tx_line, writer_line = _make_transmitter()
    tx_cone, writer_cone = _make_transmitter()
    controls = HardwareNetworkControls(_make_transceiver(**{LINE: tx_line, CONE: tx_cone}))

    controls.send_ir(b"\xff", CONE)

    assert len(writer_cone.calls) == 1
    assert len(writer_line.calls) == 0


def test_hardware_network_controls_send_ir_raises_for_unwired_emitter() -> None:
    tx, _ = _make_transmitter()
    controls = HardwareNetworkControls(_make_transceiver(**{LINE: tx}))

    with pytest.raises(ValueError):
        controls.send_ir(b"x", CONE)


def test_hardware_network_controls_send_ir_raises_for_empty_transceiver() -> None:
    controls = HardwareNetworkControls(_make_transceiver())

    with pytest.raises(ValueError):
        controls.send_ir(b"x", LINE)


def test_hardware_network_controls_send_ir_raises_when_no_transceiver_is_wired() -> None:
    controls = HardwareNetworkControls(None)

    with pytest.raises(ValueError):
        controls.send_ir(b"x", LINE)


class _RecordingIrTransceiver:
    """Fake transceiver that just records send() calls -- isolates
    HardwareNetworkControls.send_ir's delegation from InfraredTransceiver's
    own send() behaviour (covered separately in test_ir_transceiver.py)."""

    def __init__(self) -> None:
        self.calls: list[tuple[bytes, str]] = []

    def send(self, data: bytes, emitter: str) -> None:
        self.calls.append((data, emitter))


def test_hardware_network_controls_send_ir_delegates_to_the_wired_transceiver() -> None:
    transceiver = _RecordingIrTransceiver()
    controls = HardwareNetworkControls(transceiver)

    controls.send_ir(b"\x01", LINE)

    assert transceiver.calls == [(b"\x01", LINE)]


class _RecordingRadioTransport(RadioTransport):
    """Records every payload sent, in call order -- send_radio's only
    observable effect (see hardware/shared/tests/test_radio_transport.py's
    RecordingRadioTransport for the full recording fake)."""

    def __init__(self) -> None:
        self.sent: list[bytes] = []

    def send(self, data: bytes) -> None:
        self.sent.append(data)

    def receive(self) -> "tuple[int, bytes] | None":
        return None  # unused by HardwareNetworkControls.send_radio


def test_hardware_network_controls_send_radio_is_a_noop_with_no_radio_wired() -> None:
    controls = HardwareNetworkControls(None)
    controls.send_radio(b"x")  # must not raise


def test_hardware_network_controls_send_radio_delegates_to_the_wired_transport() -> None:
    transport = _RecordingRadioTransport()
    controls = HardwareNetworkControls(None, radio=transport)

    controls.send_radio(b"\xab\xcd")

    assert transport.sent == [b"\xab\xcd"]


# ---------------------------------------------------------------------------
# HardwareNetworkControls — wiring into engine.create_state (issue #608)
# ---------------------------------------------------------------------------


def test_create_state_wires_engine_network_controls() -> None:
    nc = HardwareNetworkControls(None)
    engine = GameEngine(effect_controls=EffectControls(), network_controls=nc)

    state = engine.create_state(SceneControls())

    assert state.network_controls is nc

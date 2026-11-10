from __future__ import annotations

from array import array

import pytest

from engine.capabilities import MissingCapabilityError
from engine.engine import GameEngine
from engine.network import CONE, LINE
from engine.state import EffectControls, SceneControls
from hardware.shared.ir_transceiver import InfraredTransceiver
from hardware.shared.ir_transport import InfraredTransmitter, IrTransmitGate, PulseWriter
from hardware.shared.network_controls import HardwareNetworkControls

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

    def write_pulses(self, durations: array[int]) -> None:
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


def test_send_ir_with_no_ir_raises_missing_capability_for_the_emitter() -> None:
    controls = HardwareNetworkControls(None)

    with pytest.raises(MissingCapabilityError) as raised:
        controls.send_ir(b"x", LINE)

    assert (raised.value.capabilities, raised.value.scene) == ({"ir.line"}, None)


def test_send_ir_on_an_emitter_not_wired_raises_missing_capability_for_it() -> None:
    tx, _ = _make_transmitter()
    controls = HardwareNetworkControls(_make_transceiver(**{CONE: tx}))

    with pytest.raises(MissingCapabilityError) as raised:
        controls.send_ir(b"x", LINE)

    assert (raised.value.capabilities, raised.value.scene) == ({"ir.line"}, None)


def test_send_ir_on_an_unknown_emitter_raises_value_error_naming_it() -> None:
    tx, _ = _make_transmitter()
    controls = HardwareNetworkControls(_make_transceiver(**{CONE: tx}))

    with pytest.raises(ValueError, match="laser"):
        controls.send_ir(b"x", "laser")


class _RecordingIrTransceiver:
    """Fake transceiver that just records send() calls -- isolates
    HardwareNetworkControls.send_ir's delegation from InfraredTransceiver's
    own send() behaviour (covered separately in test_ir_transceiver.py)."""

    emitters = (LINE,)

    def __init__(self) -> None:
        self.calls: list[tuple[bytes, str]] = []

    def send(self, data: bytes, emitter: str) -> None:
        self.calls.append((data, emitter))


def test_hardware_network_controls_send_ir_delegates_to_the_wired_transceiver() -> None:
    transceiver = _RecordingIrTransceiver()
    controls = HardwareNetworkControls(transceiver)

    controls.send_ir(b"\x01", LINE)

    assert transceiver.calls == [(b"\x01", LINE)]


class _RecordingRadioTransceiver:
    """Fake transceiver that just records send() calls -- isolates
    HardwareNetworkControls.send_radio's delegation from RadioTransceiver's
    own send() behaviour (covered separately in test_radio_transceiver.py)."""

    def __init__(self) -> None:
        self.sent: list[bytes] = []

    def send(self, data: bytes) -> None:
        self.sent.append(data)


def test_send_radio_with_no_radio_raises_missing_capability() -> None:
    controls = HardwareNetworkControls(None)

    with pytest.raises(MissingCapabilityError) as raised:
        controls.send_radio(b"x")

    assert (raised.value.capabilities, raised.value.scene) == ({"radio"}, None)


def test_hardware_network_controls_send_radio_delegates_to_the_wired_transceiver() -> None:
    transceiver = _RecordingRadioTransceiver()
    controls = HardwareNetworkControls(None, radio=transceiver)

    controls.send_radio(b"\xab\xcd")

    assert transceiver.sent == [b"\xab\xcd"]


# ---------------------------------------------------------------------------
# HardwareNetworkControls — wiring into engine.create_state (issue #608)
# ---------------------------------------------------------------------------


def test_create_state_wires_engine_network_controls() -> None:
    nc = HardwareNetworkControls(None)
    engine = GameEngine(effect_controls=EffectControls(), network_controls=nc)

    state = engine.create_state(SceneControls())

    assert state.network_controls is nc

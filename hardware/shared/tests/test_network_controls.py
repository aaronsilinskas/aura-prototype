from __future__ import annotations

import pytest

from engine.capabilities import MissingCapabilityError
from engine.network import CONE, LINE
from engine.state import EffectControls, GameState, SceneControls
from hardware.shared.ir_codecs.aura import AuraInfraredEncoder
from hardware.shared.ir_transceiver import InfraredTransceiver
from hardware.shared.network_controls import HardwareNetworkControls
from hardware.shared.radio_transceiver import RadioTransceiver
from hardware.shared.tests.ir_fakes import EmitterPulseWriter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _transceiver_with_emitter(emitter: str) -> tuple[InfraredTransceiver, EmitterPulseWriter]:
    """A receiver-less transceiver with only *emitter* wired, and that emitter's writer."""
    writer = EmitterPulseWriter()
    transceiver = InfraredTransceiver([], {emitter: "GP1"}, lambda _e, _pin: (writer, "fake"))
    return transceiver, writer


# ---------------------------------------------------------------------------
# HardwareNetworkControls — send_ir delegates to the wired transceiver
# ---------------------------------------------------------------------------


def test_send_ir_writes_the_encoded_payload_on_the_named_emitter() -> None:
    transceiver, writer = _transceiver_with_emitter(CONE)
    controls = HardwareNetworkControls(transceiver)

    controls.send_ir(b"\xab\xcd", CONE)

    assert writer.calls == [list(AuraInfraredEncoder().encode(b"\xab\xcd"))]


def test_send_ir_with_no_ir_raises_missing_capability_for_the_emitter() -> None:
    controls = HardwareNetworkControls(None)

    with pytest.raises(MissingCapabilityError) as raised:
        controls.send_ir(b"x", LINE)

    assert (raised.value.capabilities, raised.value.scene) == ({"ir.line"}, None)


def test_send_ir_on_an_emitter_not_wired_raises_missing_capability_for_it() -> None:
    transceiver, _ = _transceiver_with_emitter(CONE)
    controls = HardwareNetworkControls(transceiver)

    with pytest.raises(MissingCapabilityError) as raised:
        controls.send_ir(b"x", LINE)

    assert (raised.value.capabilities, raised.value.scene) == ({"ir.line"}, None)


def test_send_ir_on_an_unknown_emitter_raises_value_error_naming_it() -> None:
    transceiver, _ = _transceiver_with_emitter(CONE)
    controls = HardwareNetworkControls(transceiver)

    with pytest.raises(ValueError, match="laser"):
        controls.send_ir(b"x", "laser")


class _RecordingRadioTransceiver(RadioTransceiver):
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
# HardwareNetworkControls — handed to rules through GameState (issue #608)
# ---------------------------------------------------------------------------


def test_a_state_exposes_the_hardware_network_controls_it_is_given() -> None:
    nc = HardwareNetworkControls(None)

    state = GameState(EffectControls(), SceneControls(), nc)

    assert state.network_controls is nc

import pytest

from engine.engine import GameEngine
from engine.network import HardwareNetworkControls, NetworkEvents
from engine.state import EffectControls, GameState, NetworkControls, SceneControls

# ---------------------------------------------------------------------------
# NetworkEvents.GROUP
# ---------------------------------------------------------------------------


def test_network_events_group_name_is_net() -> None:
    assert NetworkEvents.GROUP.name == "net"


# ---------------------------------------------------------------------------
# NetworkEvents.IRReceived
# ---------------------------------------------------------------------------


def test_ir_received_event_name() -> None:
    event = NetworkEvents.IRReceived(b"hello")

    assert event.name == "ir_received"


def test_ir_received_data() -> None:
    event = NetworkEvents.IRReceived(b"hello")

    assert event.data == b"hello"


def test_ir_received_group() -> None:
    event = NetworkEvents.IRReceived(b"x")

    assert event.group is NetworkEvents.GROUP


# ---------------------------------------------------------------------------
# NetworkEvents.RadioReceived
# ---------------------------------------------------------------------------


def test_radio_received_event_name() -> None:
    event = NetworkEvents.RadioReceived(b"hello", "device-1")

    assert event.name == "radio_received"


def test_radio_received_data() -> None:
    event = NetworkEvents.RadioReceived(b"hello", "device-1")

    assert event.data == b"hello"


def test_radio_received_sender() -> None:
    event = NetworkEvents.RadioReceived(b"hello", "device-1")

    assert event.sender == "device-1"


def test_radio_received_group() -> None:
    event = NetworkEvents.RadioReceived(b"x", "dev")

    assert event.group is NetworkEvents.GROUP


# ---------------------------------------------------------------------------
# NetworkControls — abstract base raises NotImplementedError
# ---------------------------------------------------------------------------


def test_network_controls_send_ir_raises_not_implemented() -> None:
    controls = NetworkControls()

    with pytest.raises(NotImplementedError):
        controls.send_ir(b"x")


def test_network_controls_send_radio_raises_not_implemented() -> None:
    controls = NetworkControls()

    with pytest.raises(NotImplementedError):
        controls.send_radio(b"x")


# ---------------------------------------------------------------------------
# HardwareNetworkControls — concrete stub does not raise
# ---------------------------------------------------------------------------


def test_hardware_network_controls_send_ir_does_not_raise() -> None:
    controls = HardwareNetworkControls()
    controls.send_ir(b"x")  # must not raise


def test_hardware_network_controls_send_radio_does_not_raise() -> None:
    controls = HardwareNetworkControls()
    controls.send_radio(b"x")  # must not raise


# ---------------------------------------------------------------------------
# GameState — network_controls field wired from GameEngine.create_state
# ---------------------------------------------------------------------------


def test_game_state_exposes_network_controls() -> None:
    nc = NetworkControls()
    state = GameState(EffectControls(), SceneControls(), nc)

    assert state.network_controls is nc


def test_game_state_default_network_controls_is_base_type() -> None:
    state = GameState(EffectControls(), SceneControls())

    assert isinstance(state.network_controls, NetworkControls)


def test_create_state_wires_engine_network_controls() -> None:
    nc = HardwareNetworkControls()
    engine = GameEngine(effect_controls=EffectControls(), network_controls=nc)

    state = engine.create_state(SceneControls())

    assert state.network_controls is nc

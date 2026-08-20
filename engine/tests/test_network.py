import pytest

from engine.network import AREA_OF_EFFECT, CONE, IR_EMITTERS, LINE, NetworkEvents
from engine.state import EffectControls, GameState, NetworkControls, SceneControls

# ---------------------------------------------------------------------------
# Emitter constants
# ---------------------------------------------------------------------------


def test_emitter_constants_are_distinct_so_routing_is_unambiguous() -> None:
    assert LINE != CONE
    assert LINE != AREA_OF_EFFECT
    assert CONE != AREA_OF_EFFECT


def test_ir_emitters_contains_exactly_the_three_emitter_constants_in_order() -> None:
    """IR_EMITTERS is the single source every derived valid-key set and wiring
    loop reads from — it must name exactly LINE, CONE, AREA_OF_EFFECT, in that
    order (#720)."""
    assert IR_EMITTERS == (LINE, CONE, AREA_OF_EFFECT)


# ---------------------------------------------------------------------------
# NetworkEvents.GROUP
# ---------------------------------------------------------------------------


def test_network_events_group_name_is_net() -> None:
    assert NetworkEvents.GROUP.name == "net"


# ---------------------------------------------------------------------------
# NetworkEvents.IRReceived — full telemetry fields
# ---------------------------------------------------------------------------


def test_ir_received_identifies_itself_to_the_engine_as_ir_received() -> None:
    event = NetworkEvents.IRReceived(
        b"hello",
        signal_strength=0.9,
        error_margin=10,
        best_receiver=None,
    )

    assert event.name == "ir_received"


def test_ir_received_stores_payload_so_rules_can_read_it() -> None:
    event = NetworkEvents.IRReceived(
        b"hello",
        signal_strength=0.9,
        error_margin=10,
        best_receiver=None,
    )

    assert event.data == b"hello"


def test_ir_received_belongs_to_net_event_group_for_routing() -> None:
    event = NetworkEvents.IRReceived(
        b"x",
        signal_strength=0.5,
        error_margin=5,
        best_receiver=None,
    )

    assert event.group is NetworkEvents.GROUP


def test_ir_received_stores_signal_strength_from_hardware() -> None:
    event = NetworkEvents.IRReceived(
        b"x",
        signal_strength=0.75,
        error_margin=20,
        best_receiver=None,
    )

    assert event.signal_strength == 0.75


def test_ir_received_stores_error_margin_from_hardware() -> None:
    event = NetworkEvents.IRReceived(
        b"x",
        signal_strength=0.8,
        error_margin=42,
        best_receiver=None,
    )

    assert event.error_margin == 42


def test_ir_received_best_receiver_none() -> None:
    event = NetworkEvents.IRReceived(
        b"x",
        signal_strength=0.8,
        error_margin=10,
        best_receiver=None,
    )

    assert event.best_receiver is None


def test_ir_received_best_receiver_set() -> None:
    event = NetworkEvents.IRReceived(
        b"x",
        signal_strength=0.8,
        error_margin=10,
        best_receiver="receiver-A",
    )

    assert event.best_receiver == "receiver-A"


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
        controls.send_ir(b"x", LINE)


def test_network_controls_send_radio_raises_not_implemented() -> None:
    controls = NetworkControls()

    with pytest.raises(NotImplementedError):
        controls.send_radio(b"x")


def test_abstract_network_controls_has_no_poll_transmits() -> None:
    """The lifecycle pump is InfraredTransceiver-only — the abstract seam
    game rules see stays send-only."""
    assert not hasattr(NetworkControls(), "poll_transmits")


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

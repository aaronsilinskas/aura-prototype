import pytest

from engine.engine import GameEngine
from engine.network import (
    AREA_OF_EFFECT,
    CONE,
    LINE,
    HardwareNetworkControls,
    NetworkEvents,
    TransmitPump,
)
from engine.state import EffectControls, GameState, NetworkControls, SceneControls
from hardware.shared.ir_transport import InfraredTransmitter, PulseWriter

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


# ---------------------------------------------------------------------------
# Emitter constants
# ---------------------------------------------------------------------------


def test_emitter_constants_are_distinct_so_routing_is_unambiguous() -> None:
    assert LINE != CONE
    assert LINE != AREA_OF_EFFECT
    assert CONE != AREA_OF_EFFECT


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


# ---------------------------------------------------------------------------
# HardwareNetworkControls — emitter map construction and dispatch
# ---------------------------------------------------------------------------


def test_hardware_network_controls_send_ir_dispatches_correct_data() -> None:
    tx, writer = _make_transmitter()
    controls = HardwareNetworkControls({CONE: tx})

    controls.send_ir(b"\xab\xcd", CONE)

    assert writer.calls[0] == [0xAB, 0xCD]


def test_hardware_network_controls_send_ir_returns_true_when_idle() -> None:
    tx, _ = _make_transmitter()  # writer's is_busy() always reports False
    controls = HardwareNetworkControls({LINE: tx})

    assert controls.send_ir(b"\x01", LINE) is True


def test_hardware_network_controls_send_ir_returns_false_when_busy() -> None:
    class _BusyTransmitter:
        """Fake transmitter whose send() always reports buffered (busy)."""

        def send(self, data: bytes) -> bool:
            return False

        def poll(self) -> bool:
            return True

    controls = HardwareNetworkControls({LINE: _BusyTransmitter()})

    assert controls.send_ir(b"\x01", LINE) is False


def test_hardware_network_controls_send_ir_routes_to_correct_transmitter() -> None:
    tx_line, writer_line = _make_transmitter()
    tx_cone, writer_cone = _make_transmitter()
    controls = HardwareNetworkControls({LINE: tx_line, CONE: tx_cone})

    controls.send_ir(b"\xff", CONE)

    assert len(writer_cone.calls) == 1
    assert len(writer_line.calls) == 0


def test_hardware_network_controls_send_ir_raises_for_unwired_emitter() -> None:
    tx, _ = _make_transmitter()
    controls = HardwareNetworkControls({LINE: tx})

    with pytest.raises(ValueError):
        controls.send_ir(b"x", CONE)


def test_hardware_network_controls_send_ir_raises_for_empty_map() -> None:
    controls = HardwareNetworkControls({})

    with pytest.raises(ValueError):
        controls.send_ir(b"x", LINE)


class _PollCountingTransmitter:
    """Fake transmitter that just records how many times poll() was called —
    isolates HardwareNetworkControls.poll_transmits's fan-out from
    InfraredTransmitter's own poll() behaviour (covered separately)."""

    def __init__(self, busy_after_poll: bool = False) -> None:
        self.poll_calls = 0
        self._busy_after_poll = busy_after_poll

    def poll(self) -> bool:
        self.poll_calls += 1
        return self._busy_after_poll

    def send(self, data: bytes) -> bool:
        return True  # not exercised by these tests


def test_poll_transmits_polls_every_wired_transmitter() -> None:
    tx_line = _PollCountingTransmitter()
    tx_cone = _PollCountingTransmitter()
    controls = HardwareNetworkControls({LINE: tx_line, CONE: tx_cone})

    controls.poll_transmits()

    assert tx_line.poll_calls == 1
    assert tx_cone.poll_calls == 1


def test_poll_transmits_polls_each_transmitter_once_per_call() -> None:
    tx = _PollCountingTransmitter()
    controls = HardwareNetworkControls({LINE: tx})

    controls.poll_transmits()
    controls.poll_transmits()

    assert tx.poll_calls == 2


def test_poll_transmits_is_a_noop_with_no_wired_transmitters() -> None:
    controls = HardwareNetworkControls({})
    controls.poll_transmits()  # must not raise


def test_poll_transmits_maps_each_emitter_to_its_own_busy_state() -> None:
    tx_line = _PollCountingTransmitter(busy_after_poll=True)
    tx_cone = _PollCountingTransmitter(busy_after_poll=False)
    controls = HardwareNetworkControls({LINE: tx_line, CONE: tx_cone})

    result = controls.poll_transmits()

    assert result == {LINE: True, CONE: False}


def test_poll_transmits_returns_the_same_dict_instance_across_calls() -> None:
    """Pre-allocated at construction, mutated in place — no per-call allocation."""
    tx = _PollCountingTransmitter()
    controls = HardwareNetworkControls({LINE: tx})

    first = controls.poll_transmits()
    second = controls.poll_transmits()

    assert first is second


def test_poll_transmits_with_no_wired_transmitters_returns_empty_dict() -> None:
    controls = HardwareNetworkControls({})

    assert controls.poll_transmits() == {}


def test_abstract_network_controls_has_no_poll_transmits() -> None:
    """The lifecycle pump is HardwareNetworkControls-only — the abstract
    seam game rules see stays send-only."""
    assert not hasattr(NetworkControls(), "poll_transmits")


# ---------------------------------------------------------------------------
# TransmitPump — the runtime-facing declaring seam (issue #608)
# ---------------------------------------------------------------------------


def test_transmit_pump_poll_transmits_raises_not_implemented() -> None:
    pump = TransmitPump()

    with pytest.raises(NotImplementedError):
        pump.poll_transmits()


def test_hardware_network_controls_satisfies_both_network_controls_and_transmit_pump() -> None:
    controls = HardwareNetworkControls({})

    assert isinstance(controls, NetworkControls)
    assert isinstance(controls, TransmitPump)


def test_poll_transmits_through_declared_transmit_pump_type_mutates_dict_in_place() -> None:
    """Guards the runtime's actual call shape: `hw.transmit_pump` is declared
    as TransmitPump, never downcast to HardwareNetworkControls."""
    tx = _PollCountingTransmitter()
    pump: TransmitPump = HardwareNetworkControls({LINE: tx})

    first = pump.poll_transmits()
    second = pump.poll_transmits()

    assert first is second
    assert first == {LINE: False}


def test_send_radio_is_a_noop_until_hardware_is_wired() -> None:
    controls = HardwareNetworkControls({})
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
    nc = HardwareNetworkControls({})
    engine = GameEngine(effect_controls=EffectControls(), network_controls=nc)

    state = engine.create_state(SceneControls())

    assert state.network_controls is nc

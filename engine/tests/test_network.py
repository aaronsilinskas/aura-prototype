from engine.network import NetworkEvents


def test_network_group_identifier_is_net():
    assert NetworkEvents.GROUP.name == "net"


def test_ir_received_is_identified_as_ir_received():
    event = NetworkEvents.IRReceived(b"hello")
    assert event.name == "ir_received"


def test_ir_received_carries_packet_data():
    event = NetworkEvents.IRReceived(b"hello")
    assert event.data == b"hello"


def test_ir_received_belongs_to_network_group():
    event = NetworkEvents.IRReceived(b"hello")
    assert event.group is NetworkEvents.GROUP


def test_radio_received_is_identified_as_radio_received():
    event = NetworkEvents.RadioReceived(b"hello", "device-1")
    assert event.name == "radio_received"


def test_radio_received_carries_packet_data():
    event = NetworkEvents.RadioReceived(b"hello", "device-1")
    assert event.data == b"hello"


def test_radio_received_carries_sender_identifier():
    event = NetworkEvents.RadioReceived(b"hello", "device-1")
    assert event.sender == "device-1"


def test_radio_received_belongs_to_network_group():
    event = NetworkEvents.RadioReceived(b"hello", "device-1")
    assert event.group is NetworkEvents.GROUP

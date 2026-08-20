"""Behaviour-driven tests for the RadioTransport port (hardware/shared/radio_transport.py).

Covers:
- RadioTransport base-class contract (send / receive raise NotImplementedError)
"""

import pytest

from hardware.shared.radio_transport import RadioTransport

# ---------------------------------------------------------------------------
# Port contract
# ---------------------------------------------------------------------------


def test_radio_transport_send_base_raises_not_implemented():
    transport = RadioTransport()

    with pytest.raises(NotImplementedError):
        transport.send(b"\xab")


def test_radio_transport_receive_base_raises_not_implemented():
    transport = RadioTransport()

    with pytest.raises(NotImplementedError):
        transport.receive()

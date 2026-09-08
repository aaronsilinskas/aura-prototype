"""Behaviour-driven tests for SdSyncServer's read primitive.

The full request/response/chunk/CRC protocol is exercised end-to-end by the
loopback test in ``scripts/tests/test_sd_sync_loopback.py``, which drives
``SdSyncServer`` through ``SdSyncClient`` -- the seam that matters for the
protocol as a whole. These tests cover ``read`` directly, the one piece of
server behaviour meaningful in isolation from the wire.
"""

from hardware.shared.sd_sync_server import SdSyncServer
from hardware.shared.tests.helpers import FakeDeviceStorage


def test_read_returns_the_exact_bytes_of_a_written_file():
    storage = FakeDeviceStorage()
    storage.write_bytes("aura-state.json", b'{"scene": "tag"}')
    server = SdSyncServer(storage)

    assert server.read("aura-state.json") == b'{"scene": "tag"}'


def test_read_returns_none_for_a_never_written_path():
    server = SdSyncServer(FakeDeviceStorage())

    assert server.read("missing.json") is None

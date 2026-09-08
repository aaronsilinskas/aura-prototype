"""Behaviour-driven tests for SdSyncServer's read/write primitives.

The full request/response/chunk/CRC protocol is exercised end-to-end by the
loopback test in ``scripts/tests/test_sd_sync_loopback.py``, which drives
``SdSyncServer`` through ``SdSyncClient`` -- the seam that matters for the
protocol as a whole. These tests cover ``read``/``write`` directly, the two
pieces of server behaviour meaningful in isolation from the wire.
"""

from hardware.shared.sd_sync_protocol import CHUNK_SIZE
from hardware.shared.sd_sync_server import SdSyncServer
from hardware.shared.tests.helpers import FakeDeviceStorage


def test_read_returns_the_exact_bytes_of_a_written_file():
    storage = FakeDeviceStorage()
    storage.write_bytes("aura-state.json", b'{"scene": "tag"}')
    server = SdSyncServer(storage)

    assert b"".join(server.read("aura-state.json")) == b'{"scene": "tag"}'


def test_read_returns_none_for_a_never_written_path():
    server = SdSyncServer(FakeDeviceStorage())

    assert server.read("missing.json") is None


def test_read_yields_more_than_one_chunk_for_content_larger_than_chunk_size():
    storage = FakeDeviceStorage()
    storage.write_bytes("log.txt", b"x" * (CHUNK_SIZE + 1))
    server = SdSyncServer(storage)

    chunks = list(server.read("log.txt"))

    assert len(chunks) > 1


def test_write_stores_the_exact_bytes_of_the_streamed_chunks():
    storage = FakeDeviceStorage()
    server = SdSyncServer(storage)

    server.write("aura-state.json", [b'{"scene": ', b'"tag"}'])

    assert storage.read_bytes("aura-state.json") == b'{"scene": "tag"}'


def test_write_creates_missing_parent_directories():
    storage = FakeDeviceStorage()
    server = SdSyncServer(storage)

    server.write("aura_packs/scenes/tag/scene.json", [b"{}"])

    assert storage.read_bytes("aura_packs/scenes/tag/scene.json") == b"{}"

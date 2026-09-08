"""Behaviour-driven tests for SdSyncServer's read and list primitives.

The full request/response/chunk/CRC protocol is exercised end-to-end by the
loopback tests in ``scripts/tests/test_sd_sync_loopback.py``, which drive
``SdSyncServer`` through ``SdSyncClient`` -- the seam that matters for the
protocol as a whole. These tests cover ``read`` and ``list`` directly, the
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


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


def test_list_returns_every_seeded_file_at_the_card_root():
    storage = FakeDeviceStorage()
    storage.write_bytes("aura-state.json", b'{"scene": "tag"}')
    storage.write_bytes("aura_packs/scenes/tag/scene.json", b"{}")
    server = SdSyncServer(storage)

    assert server.list() == [
        ("aura-state.json", 16),
        ("aura_packs/scenes/tag/scene.json", 2),
    ]


def test_list_of_a_named_subpath_scopes_to_files_beneath_it():
    storage = FakeDeviceStorage()
    storage.write_bytes("aura-state.json", b'{"scene": "tag"}')
    storage.write_bytes("aura_packs/scenes/tag/scene.json", b"{}")
    storage.write_bytes("aura_packs/scenes/lobby/scene.json", b"{}")
    server = SdSyncServer(storage)

    assert server.list("aura_packs/scenes/tag") == [("aura_packs/scenes/tag/scene.json", 2)]


def test_list_of_an_empty_subpath_returns_no_entries():
    storage = FakeDeviceStorage()
    storage.write_bytes("aura-state.json", b'{"scene": "tag"}')
    server = SdSyncServer(storage)

    assert server.list("aura_packs/scenes") == []


def test_list_with_no_sd_configured_returns_none_rather_than_raising():
    server = SdSyncServer(None)

    assert server.list() is None

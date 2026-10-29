"""Behaviour-driven tests for SdSyncServer's read, write, and list primitives.

The full request/response/chunk/CRC protocol is exercised end-to-end by the
loopback tests in ``scripts/tests/test_sd_sync_loopback.py``, which drive
``SdSyncServer`` through ``SdSyncClient`` -- the seam that matters for the
protocol as a whole. These tests cover ``read``, ``write`` and ``list``
directly, the pieces of server behaviour meaningful in isolation from the wire,
plus ``serve_one``'s request-verb dispatch (#930) -- the piece a device-side
loop needs to service a mix of verbs over one connection.
"""

import pytest

from hardware.shared.sd_sync_protocol import (
    CHUNK_SIZE,
    Frame,
    Transport,
    decode_frame,
    decode_listing,
    encode_frame,
)
from hardware.shared.sd_sync_server import SdSyncServer


def test_read_returns_the_exact_bytes_of_a_written_file(device_storage):
    device_storage.write_bytes("aura-state.json", b'{"scene": "tag"}')
    server = SdSyncServer(device_storage)

    assert b"".join(server.read("aura-state.json")) == b'{"scene": "tag"}'


def test_read_returns_none_for_a_never_written_path(device_storage):
    server = SdSyncServer(device_storage)

    assert server.read("missing.json") is None


def test_read_yields_more_than_one_chunk_for_content_larger_than_chunk_size(device_storage):
    device_storage.write_bytes("log.txt", b"x" * (CHUNK_SIZE + 1))
    server = SdSyncServer(device_storage)

    chunks = list(server.read("log.txt"))

    assert len(chunks) > 1


# ---------------------------------------------------------------------------
# write
# ---------------------------------------------------------------------------


def test_write_stores_the_exact_bytes_of_the_streamed_chunks(device_storage):
    server = SdSyncServer(device_storage)

    server.write("aura-state.json", [b'{"scene": ', b'"tag"}'])

    assert device_storage.read_bytes("aura-state.json") == b'{"scene": "tag"}'


def test_write_creates_missing_parent_directories(device_storage):
    server = SdSyncServer(device_storage)

    server.write("aura_packs/scenes/tag/scene.json", [b"{}"])

    assert device_storage.read_bytes("aura_packs/scenes/tag/scene.json") == b"{}"


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


def test_list_returns_every_seeded_file_at_the_card_root(device_storage):
    device_storage.write_bytes("aura-state.json", b'{"scene": "tag"}')
    device_storage.write_bytes("aura_packs/scenes/tag/scene.json", b"{}")
    server = SdSyncServer(device_storage)

    assert server.list() == [
        ("aura-state.json", 16),
        ("aura_packs/scenes/tag/scene.json", 2),
    ]


def test_list_of_a_named_subpath_scopes_to_files_beneath_it(device_storage):
    device_storage.write_bytes("aura-state.json", b'{"scene": "tag"}')
    device_storage.write_bytes("aura_packs/scenes/tag/scene.json", b"{}")
    device_storage.write_bytes("aura_packs/scenes/lobby/scene.json", b"{}")
    server = SdSyncServer(device_storage)

    assert server.list("aura_packs/scenes/tag") == [("aura_packs/scenes/tag/scene.json", 2)]


def test_list_of_an_empty_subpath_returns_no_entries(device_storage):
    device_storage.write_bytes("aura-state.json", b'{"scene": "tag"}')
    server = SdSyncServer(device_storage)

    assert server.list("aura_packs/scenes") == []


def test_list_with_no_sd_configured_returns_none_rather_than_raising():
    server = SdSyncServer(None)

    assert server.list() is None


# ---------------------------------------------------------------------------
# serve_one -- request-verb dispatch (#930)
# ---------------------------------------------------------------------------


class _ScriptedTransport(Transport):
    """Test double replaying pre-recorded ``recv()`` lines; records every ``send()``."""

    def __init__(self, recv_lines: list[bytes]) -> None:
        self._recv_lines = list(recv_lines)
        self.sent: list[bytes] = []

    def send(self, line: bytes) -> None:
        self.sent.append(line)

    def recv(self) -> bytes:
        return self._recv_lines.pop(0)


def test_serve_one_services_a_list_request(device_storage):
    device_storage.write_bytes("aura-state.json", b'{"scene": "tag"}')
    server = SdSyncServer(device_storage)
    transport = _ScriptedTransport([encode_frame(Frame("req", "list "))])

    server.serve_one(transport)

    response = decode_frame(transport.sent[0])
    assert decode_listing(response.payload) == [("aura-state.json", 16)]


def test_serve_one_services_a_pull_request():
    server = SdSyncServer(None)
    transport = _ScriptedTransport([encode_frame(Frame("req", "pull missing.json"))])

    server.serve_one(transport)

    assert decode_frame(transport.sent[0]).text == "no_storage"


def test_serve_one_services_a_push_request():
    server = SdSyncServer(None)
    transport = _ScriptedTransport([encode_frame(Frame("req", "push new.json"))])

    server.serve_one(transport)

    assert decode_frame(transport.sent[0]).text == "no_storage"


def test_serve_one_raises_for_an_unrecognized_verb():
    server = SdSyncServer(None)
    transport = _ScriptedTransport([encode_frame(Frame("req", "frobnicate x"))])

    with pytest.raises(ValueError, match="frobnicate"):
        server.serve_one(transport)

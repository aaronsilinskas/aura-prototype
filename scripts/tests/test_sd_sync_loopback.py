"""Behaviour-driven tests for the SD-sync protocol, driven end-to-end over a loopback.

Wires ``SdSyncClient`` to ``SdSyncServer`` over an in-memory ``Transport`` pair
(a queue in each direction, the server driven on a background thread), backed by
``FakeDeviceStorage`` -- the single highest seam for this protocol: one test
exercises request/response framing, chunked stop-and-wait streaming, and
per-file CRC-32 verification together, in CPython, with no device.

No frame bytes or wire grammar are asserted directly -- only outcomes visible
to a caller: the bytes written to the host path or the fake SD storage, and
which exception (if any) ``pull``/``push`` raises.
"""

import json
import queue
import threading
from pathlib import Path

import pytest

from hardware.shared.sd_sync_protocol import (
    CHUNK_SIZE,
    Frame,
    Transport,
    decode_frame,
    encode_frame,
)
from hardware.shared.sd_sync_server import SdSyncServer
from hardware.shared.tests.helpers import FakeDeviceStorage
from scripts.sd_sync_client import (
    SdSyncClient,
    SdSyncIntegrityError,
    SdSyncNoStorageError,
    SdSyncNotFoundError,
)

# ---------------------------------------------------------------------------
# Loopback wiring
# ---------------------------------------------------------------------------


class _QueueTransport(Transport):
    """One end of a two-queue in-memory ``Transport`` pair."""

    def __init__(self, send_q: "queue.Queue[bytes]", recv_q: "queue.Queue[bytes]") -> None:
        self._send_q = send_q
        self._recv_q = recv_q

    def send(self, line: bytes) -> None:
        self._send_q.put(line)

    def recv(self) -> bytes:
        return self._recv_q.get()


class _CorruptingTransport(Transport):
    """Wraps a ``Transport``, flipping a byte in the first *corrupt_count* chunk payloads sent.

    Test-only fault injection standing in for a bit-flip in transit -- the
    means by which the CRC-mismatch-and-retry tests force a mismatch without
    reaching into the client or server's internals.
    """

    def __init__(self, inner: Transport, corrupt_count: int) -> None:
        self._inner = inner
        self._corrupt_remaining = corrupt_count

    def send(self, line: bytes) -> None:
        frame = decode_frame(line)
        if frame.kind == "chunk" and self._corrupt_remaining > 0:
            self._corrupt_remaining -= 1
            corrupted = bytes([frame.payload[0] ^ 0xFF]) + frame.payload[1:]
            line = encode_frame(Frame(frame.kind, frame.text, corrupted))
        self._inner.send(line)

    def recv(self) -> bytes:
        return self._inner.recv()


class _CountingTransport(Transport):
    """Wraps a ``Transport``, counting sent frames by ``kind`` for behaviour-level assertions."""

    def __init__(self, inner: Transport) -> None:
        self._inner = inner
        self.sent_kind_counts: dict[str, int] = {}

    def send(self, line: bytes) -> None:
        kind = decode_frame(line).kind
        self.sent_kind_counts[kind] = self.sent_kind_counts.get(kind, 0) + 1
        self._inner.send(line)

    def recv(self) -> bytes:
        return self._inner.recv()


def _serve_forever(server: SdSyncServer, transport: Transport, verb: str) -> None:
    serve_one = {
        "pull": server.serve_pull,
        "push": server.serve_push,
        "list": server.serve_list,
    }[verb]
    while True:
        serve_one(transport)


def make_loopback_client(
    storage: "FakeDeviceStorage | None",
    *,
    verb: str = "pull",
    server_side_wrapper=None,
    client_side_wrapper=None,
    **client_kwargs,
) -> tuple[SdSyncClient, _CountingTransport]:
    """Wire a fresh ``SdSyncClient`` to a fresh ``SdSyncServer(storage)`` over a loopback.

    The server runs on a background daemon thread, blocking on its transport's
    ``recv`` between requests -- the same shape a real serial link has, just
    in-memory. *verb* picks which of the server's per-verb serve methods the
    thread drives -- ``"pull"`` (default), ``"push"``, or ``"list"`` (a test
    only ever exercises one verb per client, so there is no need for the server
    to dispatch by request text itself). Returns the client and a counting
    wrapper around its send side, for tests that assert on how many frames of
    each kind were exchanged.
    """
    to_server: queue.Queue[bytes] = queue.Queue()
    to_client: queue.Queue[bytes] = queue.Queue()

    inner_client_transport: Transport = _QueueTransport(send_q=to_server, recv_q=to_client)
    if client_side_wrapper is not None:
        inner_client_transport = client_side_wrapper(inner_client_transport)
    client_transport = _CountingTransport(inner_client_transport)

    server_transport: Transport = _QueueTransport(send_q=to_client, recv_q=to_server)
    if server_side_wrapper is not None:
        server_transport = server_side_wrapper(server_transport)

    server = SdSyncServer(storage)
    thread = threading.Thread(
        target=_serve_forever, args=(server, server_transport, verb), daemon=True
    )
    thread.start()

    return SdSyncClient(client_transport, **client_kwargs), client_transport


# ---------------------------------------------------------------------------
# Exact round-trip
# ---------------------------------------------------------------------------


def test_pull_writes_the_exact_sd_bytes_to_the_host_path(tmp_path: Path):
    storage = FakeDeviceStorage()
    storage.write_bytes("aura-state.json", b'{"scene": "tag", "return_to": "lobby"}')
    client, _ = make_loopback_client(storage)
    host_path = tmp_path / "aura-state.json"

    client.pull("aura-state.json", str(host_path))

    assert host_path.read_bytes() == b'{"scene": "tag", "return_to": "lobby"}'


def test_pull_preserves_a_relative_subpath_by_creating_missing_host_directories(tmp_path: Path):
    storage = FakeDeviceStorage()
    storage.write_bytes("aura_packs/scenes/tag/scene.json", b"{}")
    client, _ = make_loopback_client(storage)
    host_path = tmp_path / "aura_packs" / "scenes" / "tag" / "scene.json"

    client.pull("aura_packs/scenes/tag/scene.json", str(host_path))

    assert host_path.read_bytes() == b"{}"


# ---------------------------------------------------------------------------
# Binary payload
# ---------------------------------------------------------------------------


def test_pull_round_trips_a_binary_payload_intact(tmp_path: Path):
    binary_content = bytes(range(256)) * 4  # every byte value, including NUL and 0x0A/0x0D
    storage = FakeDeviceStorage()
    storage.write_bytes("capture.bin", binary_content)
    client, _ = make_loopback_client(storage)
    host_path = tmp_path / "capture.bin"

    client.pull("capture.bin", str(host_path))

    assert host_path.read_bytes() == binary_content


# ---------------------------------------------------------------------------
# Chunked / large payload
# ---------------------------------------------------------------------------


def test_pull_round_trips_a_large_payload_through_multiple_chunks(tmp_path: Path):
    large_content = b"0123456789abcdef" * (CHUNK_SIZE * 5)  # several chunk-sizes long
    storage = FakeDeviceStorage()
    storage.write_bytes("log.txt", large_content)
    client, transport = make_loopback_client(storage)
    host_path = tmp_path / "log.txt"

    client.pull("log.txt", str(host_path))

    assert host_path.read_bytes() == large_content
    expected_chunk_count = -(-len(large_content) // CHUNK_SIZE)  # ceil division
    assert transport.sent_kind_counts["ack"] == expected_chunk_count


def test_pull_of_a_small_payload_sends_exactly_one_ack(tmp_path: Path):
    storage = FakeDeviceStorage()
    storage.write_bytes("small.txt", b"hello")
    client, transport = make_loopback_client(storage)
    host_path = tmp_path / "small.txt"

    client.pull("small.txt", str(host_path))

    assert transport.sent_kind_counts["ack"] == 1


# ---------------------------------------------------------------------------
# CRC-32 verification, retry, and exhausted-retry failure
# ---------------------------------------------------------------------------


def test_pull_retries_and_succeeds_after_one_transient_checksum_mismatch(tmp_path: Path):
    storage = FakeDeviceStorage()
    storage.write_bytes("flaky.json", b'{"scene": "tag"}')
    client, _ = make_loopback_client(
        storage,
        server_side_wrapper=lambda inner: _CorruptingTransport(inner, corrupt_count=1),
    )
    host_path = tmp_path / "flaky.json"

    client.pull("flaky.json", str(host_path))

    assert host_path.read_bytes() == b'{"scene": "tag"}'


def test_pull_raises_integrity_error_after_exhausting_retries(tmp_path: Path):
    storage = FakeDeviceStorage()
    storage.write_bytes("corrupt.json", b'{"scene": "tag"}')
    client, _ = make_loopback_client(
        storage,
        server_side_wrapper=lambda inner: _CorruptingTransport(inner, corrupt_count=10),
        max_attempts=3,
    )
    host_path = tmp_path / "corrupt.json"

    with pytest.raises(SdSyncIntegrityError, match=r"corrupt\.json"):
        client.pull("corrupt.json", str(host_path))


def test_pull_leaves_no_host_file_after_exhausting_retries(tmp_path: Path):
    storage = FakeDeviceStorage()
    storage.write_bytes("corrupt.json", b'{"scene": "tag"}')
    client, _ = make_loopback_client(
        storage,
        server_side_wrapper=lambda inner: _CorruptingTransport(inner, corrupt_count=10),
        max_attempts=3,
    )
    host_path = tmp_path / "corrupt.json"

    with pytest.raises(SdSyncIntegrityError):
        client.pull("corrupt.json", str(host_path))

    assert not host_path.exists()


# ---------------------------------------------------------------------------
# Not found / no SD configured
# ---------------------------------------------------------------------------


def test_pull_of_a_nonexistent_sd_path_raises_not_found(tmp_path: Path):
    client, _ = make_loopback_client(FakeDeviceStorage())
    host_path = tmp_path / "missing.json"

    with pytest.raises(SdSyncNotFoundError, match=r"missing\.json"):
        client.pull("missing.json", str(host_path))


def test_pull_of_a_nonexistent_sd_path_leaves_no_host_file(tmp_path: Path):
    client, _ = make_loopback_client(FakeDeviceStorage())
    host_path = tmp_path / "missing.json"

    with pytest.raises(SdSyncNotFoundError):
        client.pull("missing.json", str(host_path))

    assert not host_path.exists()


def test_pull_with_no_sd_configured_raises_no_storage_error(tmp_path: Path):
    client, _ = make_loopback_client(storage=None)
    host_path = tmp_path / "aura-state.json"

    with pytest.raises(SdSyncNoStorageError, match=r"aura-state\.json"):
        client.pull("aura-state.json", str(host_path))


def test_pull_with_no_sd_configured_leaves_no_host_file(tmp_path: Path):
    client, _ = make_loopback_client(storage=None)
    host_path = tmp_path / "aura-state.json"

    with pytest.raises(SdSyncNoStorageError):
        client.pull("aura-state.json", str(host_path))

    assert not host_path.exists()


# ---------------------------------------------------------------------------
# Push -- exact round-trip
# ---------------------------------------------------------------------------


def test_push_writes_the_exact_host_bytes_to_the_named_sd_path(tmp_path: Path):
    storage = FakeDeviceStorage()
    client, _ = make_loopback_client(storage, verb="push")
    host_path = tmp_path / "aura-state.json"
    host_path.write_bytes(b'{"scene": "tag", "return_to": "lobby"}')

    client.push(str(host_path), "aura-state.json")

    assert storage.read_bytes("aura-state.json") == b'{"scene": "tag", "return_to": "lobby"}'


def test_push_into_a_not_yet_existing_sd_subtree_creates_missing_parent_directories(
    tmp_path: Path,
):
    storage = FakeDeviceStorage()
    client, _ = make_loopback_client(storage, verb="push")
    host_path = tmp_path / "scene.json"
    host_path.write_bytes(b"{}")

    client.push(str(host_path), "aura_packs/scenes/tag/scene.json")

    assert storage.read_bytes("aura_packs/scenes/tag/scene.json") == b"{}"


def test_push_preserves_the_named_sd_path_even_when_the_host_layout_differs(tmp_path: Path):
    storage = FakeDeviceStorage()
    client, _ = make_loopback_client(storage, verb="push")
    host_path = tmp_path / "local-copy" / "state.json"
    host_path.parent.mkdir()
    host_path.write_bytes(b'{"scene": "tag"}')

    client.push(str(host_path), "aura-state.json")

    assert storage.read_bytes("aura-state.json") == b'{"scene": "tag"}'
    assert storage.read_bytes("local-copy/state.json") is None


# ---------------------------------------------------------------------------
# Push -- binary payload
# ---------------------------------------------------------------------------


def test_push_round_trips_a_binary_payload_intact(tmp_path: Path):
    binary_content = bytes(range(256)) * 4  # every byte value, including NUL and 0x0A/0x0D
    storage = FakeDeviceStorage()
    client, _ = make_loopback_client(storage, verb="push")
    host_path = tmp_path / "capture.bin"
    host_path.write_bytes(binary_content)

    client.push(str(host_path), "capture.bin")

    assert storage.read_bytes("capture.bin") == binary_content


# ---------------------------------------------------------------------------
# Push -- chunked / large payload
# ---------------------------------------------------------------------------


def test_push_round_trips_a_large_payload_through_multiple_chunks(tmp_path: Path):
    large_content = b"0123456789abcdef" * (CHUNK_SIZE * 5)  # several chunk-sizes long
    storage = FakeDeviceStorage()
    client, transport = make_loopback_client(storage, verb="push")
    host_path = tmp_path / "log.txt"
    host_path.write_bytes(large_content)

    client.push(str(host_path), "log.txt")

    assert storage.read_bytes("log.txt") == large_content
    expected_chunk_count = -(-len(large_content) // CHUNK_SIZE)  # ceil division
    assert transport.sent_kind_counts["chunk"] == expected_chunk_count


def test_push_of_a_small_payload_sends_exactly_one_chunk(tmp_path: Path):
    storage = FakeDeviceStorage()
    client, transport = make_loopback_client(storage, verb="push")
    host_path = tmp_path / "small.txt"
    host_path.write_bytes(b"hello")

    client.push(str(host_path), "small.txt")

    assert transport.sent_kind_counts["chunk"] == 1


# ---------------------------------------------------------------------------
# Push -- CRC-32 verification, retry, and exhausted-retry failure
# ---------------------------------------------------------------------------


def test_push_retries_and_succeeds_after_one_transient_checksum_mismatch(tmp_path: Path):
    storage = FakeDeviceStorage()
    client, _ = make_loopback_client(
        storage,
        verb="push",
        client_side_wrapper=lambda inner: _CorruptingTransport(inner, corrupt_count=1),
    )
    host_path = tmp_path / "flaky.json"
    host_path.write_bytes(b'{"scene": "tag"}')

    client.push(str(host_path), "flaky.json")

    assert storage.read_bytes("flaky.json") == b'{"scene": "tag"}'


def test_push_raises_integrity_error_after_exhausting_retries(tmp_path: Path):
    storage = FakeDeviceStorage()
    client, _ = make_loopback_client(
        storage,
        verb="push",
        client_side_wrapper=lambda inner: _CorruptingTransport(inner, corrupt_count=10),
        max_attempts=3,
    )
    host_path = tmp_path / "corrupt.json"
    host_path.write_bytes(b'{"scene": "tag"}')

    with pytest.raises(SdSyncIntegrityError, match=r"corrupt\.json"):
        client.push(str(host_path), "corrupt.json")


def test_push_after_exhausting_retries_leaves_prior_sd_content_intact(tmp_path: Path):
    storage = FakeDeviceStorage()
    storage.write_bytes("corrupt.json", b'{"scene": "original"}')
    client, _ = make_loopback_client(
        storage,
        verb="push",
        client_side_wrapper=lambda inner: _CorruptingTransport(inner, corrupt_count=10),
        max_attempts=3,
    )
    host_path = tmp_path / "corrupt.json"
    host_path.write_bytes(b'{"scene": "tag"}')

    with pytest.raises(SdSyncIntegrityError):
        client.push(str(host_path), "corrupt.json")

    assert storage.read_bytes("corrupt.json") == b'{"scene": "original"}'


# ---------------------------------------------------------------------------
# Push -- no SD configured
# ---------------------------------------------------------------------------


def test_push_with_no_sd_configured_raises_no_storage_error(tmp_path: Path):
    client, _ = make_loopback_client(storage=None, verb="push")
    host_path = tmp_path / "aura-state.json"
    host_path.write_bytes(b"{}")

    with pytest.raises(SdSyncNoStorageError, match=r"aura-state\.json"):
        client.push(str(host_path), "aura-state.json")


# ---------------------------------------------------------------------------
# Pull -> edit -> push round trip (#925's motivating scene-change scenario)
# ---------------------------------------------------------------------------


def test_pull_edit_push_round_trip_changes_scene_and_preserves_return_to(tmp_path: Path):
    storage = FakeDeviceStorage()
    storage.write_bytes("aura-state.json", b'{"scene": "lobby", "return_to": "lobby"}')
    host_path = tmp_path / "aura-state.json"

    pull_client, _ = make_loopback_client(storage, verb="pull")
    pull_client.pull("aura-state.json", str(host_path))

    state = json.loads(host_path.read_text())
    state["scene"] = "tag"
    host_path.write_text(json.dumps(state))

    push_client, _ = make_loopback_client(storage, verb="push")
    push_client.push(str(host_path), "aura-state.json")

    assert json.loads(storage.read_bytes("aura-state.json")) == {
        "scene": "tag",
        "return_to": "lobby",
    }


# ---------------------------------------------------------------------------
# list_files
# ---------------------------------------------------------------------------


def test_list_files_returns_every_seeded_path_and_size_at_the_card_root():
    storage = FakeDeviceStorage()
    storage.write_bytes("aura-state.json", b'{"scene": "tag"}')
    storage.write_bytes("aura_packs/scenes/tag/scene.json", b"{}")
    client, _ = make_loopback_client(storage, verb="list")

    assert client.list_files() == [
        ("aura-state.json", 16),
        ("aura_packs/scenes/tag/scene.json", 2),
    ]


def test_list_files_of_a_named_subpath_scopes_to_files_beneath_it():
    storage = FakeDeviceStorage()
    storage.write_bytes("aura_packs/scenes/tag/scene.json", b"{}")
    storage.write_bytes("aura_packs/scenes/lobby/scene.json", b"{}")
    client, _ = make_loopback_client(storage, verb="list")

    assert client.list_files("aura_packs/scenes/tag") == [("aura_packs/scenes/tag/scene.json", 2)]


def test_list_files_of_an_empty_subpath_returns_no_entries():
    storage = FakeDeviceStorage()
    storage.write_bytes("aura-state.json", b'{"scene": "tag"}')
    client, _ = make_loopback_client(storage, verb="list")

    assert client.list_files("aura_packs/scenes") == []


def test_list_files_with_no_sd_configured_raises_no_storage_error():
    client, _ = make_loopback_client(storage=None, verb="list")

    with pytest.raises(SdSyncNoStorageError):
        client.list_files()

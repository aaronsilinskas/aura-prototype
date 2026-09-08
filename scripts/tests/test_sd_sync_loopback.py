"""Behaviour-driven tests for the SD-sync protocol, driven end-to-end over a loopback.

Wires ``SdSyncClient`` to ``SdSyncServer`` over an in-memory ``Transport`` pair
(a queue in each direction, the server driven on a background thread), backed by
``FakeDeviceStorage`` -- the single highest seam for this protocol: one test
exercises request/response framing, chunked stop-and-wait streaming, and
per-file CRC-32 verification together, in CPython, with no device.

No frame bytes or wire grammar are asserted directly -- only outcomes visible
to a caller: the bytes written to the host path, and which exception (if any)
``pull`` raises.
"""

import queue
import threading
from collections.abc import Callable
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


def _serve_forever(
    server: SdSyncServer,
    transport: Transport,
    serve_method: Callable[[SdSyncServer, Transport], None],
) -> None:
    while True:
        serve_method(server, transport)


def make_loopback_client(
    storage: "FakeDeviceStorage | None",
    *,
    server_side_wrapper=None,
    serve_method: Callable[[SdSyncServer, Transport], None] = SdSyncServer.serve_pull,
    **client_kwargs,
) -> tuple[SdSyncClient, _CountingTransport]:
    """Wire a fresh ``SdSyncClient`` to a fresh ``SdSyncServer(storage)`` over a loopback.

    The server runs on a background daemon thread, blocking on its transport's
    ``recv`` between requests -- the same shape a real serial link has, just
    in-memory. Returns the client and a counting wrapper around its send side,
    for tests that assert on how many frames of each kind were exchanged.
    *serve_method* is the unbound ``SdSyncServer`` verb method to loop on
    (:meth:`SdSyncServer.serve_pull` by default; pass
    :meth:`SdSyncServer.serve_list` for the list verb).
    """
    to_server: queue.Queue[bytes] = queue.Queue()
    to_client: queue.Queue[bytes] = queue.Queue()

    client_transport = _CountingTransport(_QueueTransport(send_q=to_server, recv_q=to_client))
    server_transport: Transport = _QueueTransport(send_q=to_client, recv_q=to_server)
    if server_side_wrapper is not None:
        server_transport = server_side_wrapper(server_transport)

    server = SdSyncServer(storage)
    thread = threading.Thread(
        target=_serve_forever, args=(server, server_transport, serve_method), daemon=True
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
# list_files
# ---------------------------------------------------------------------------


def test_list_files_returns_every_seeded_path_and_size_at_the_card_root():
    storage = FakeDeviceStorage()
    storage.write_bytes("aura-state.json", b'{"scene": "tag"}')
    storage.write_bytes("aura_packs/scenes/tag/scene.json", b"{}")
    client, _ = make_loopback_client(storage, serve_method=SdSyncServer.serve_list)

    assert client.list_files() == [
        ("aura-state.json", 16),
        ("aura_packs/scenes/tag/scene.json", 2),
    ]


def test_list_files_of_a_named_subpath_scopes_to_files_beneath_it():
    storage = FakeDeviceStorage()
    storage.write_bytes("aura_packs/scenes/tag/scene.json", b"{}")
    storage.write_bytes("aura_packs/scenes/lobby/scene.json", b"{}")
    client, _ = make_loopback_client(storage, serve_method=SdSyncServer.serve_list)

    assert client.list_files("aura_packs/scenes/tag") == [("aura_packs/scenes/tag/scene.json", 2)]


def test_list_files_of_an_empty_subpath_returns_no_entries():
    storage = FakeDeviceStorage()
    storage.write_bytes("aura-state.json", b'{"scene": "tag"}')
    client, _ = make_loopback_client(storage, serve_method=SdSyncServer.serve_list)

    assert client.list_files("aura_packs/scenes") == []


def test_list_files_with_no_sd_configured_raises_no_storage_error():
    client, _ = make_loopback_client(storage=None, serve_method=SdSyncServer.serve_list)

    with pytest.raises(SdSyncNoStorageError):
        client.list_files()

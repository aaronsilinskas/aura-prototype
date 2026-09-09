"""Tests for scripts.sd_sync's pure arg-parsing/dispatch wiring, and data-port selection.

``dispatch`` is exercised against a real ``SdSyncClient`` wired to an
in-memory loopback ``Transport`` (mirroring ``test_sd_sync_loopback.py``'s
harness) -- no real device or serial I/O. The live ``SerialTransport``/
``find_data_port`` glue in ``scripts.sd_sync_transport`` is hardware-validated
and not exercised here, except for the pure ``select_data_port`` selection
rule.
"""

import io
import queue
import threading
from pathlib import Path

import pytest

from hardware.shared.sd_sync_protocol import Transport
from hardware.shared.sd_sync_server import SdSyncServer
from hardware.shared.tests.helpers import FakeDeviceStorage
from scripts.sd_sync import build_client, dispatch, parse_args
from scripts.sd_sync_client import SdSyncNotFoundError
from scripts.sd_sync_transport import SdSyncPortError, select_data_port

# ---------------------------------------------------------------------------
# select_data_port
# ---------------------------------------------------------------------------


class _FakeComport:
    def __init__(self, device: str) -> None:
        self.device = device


def test_select_data_port_auto_selects_the_single_match() -> None:
    port = select_data_port([_FakeComport("/dev/tty.usbmodem1")])

    assert port == "/dev/tty.usbmodem1"


def test_select_data_port_raises_when_no_ports_found() -> None:
    with pytest.raises(SdSyncPortError, match="--port"):
        select_data_port([])


def test_select_data_port_raises_when_multiple_ports_found() -> None:
    with pytest.raises(SdSyncPortError, match="--port"):
        select_data_port([_FakeComport("/dev/tty.usbmodem1"), _FakeComport("/dev/tty.usbmodem2")])


def test_select_data_port_explicit_port_wins_over_a_single_auto_detected_match() -> None:
    port = select_data_port([_FakeComport("/dev/tty.usbmodem1")], explicit_port="/dev/tty.explicit")

    assert port == "/dev/tty.explicit"


def test_select_data_port_explicit_port_wins_over_ambiguous_auto_detection() -> None:
    port = select_data_port(
        [_FakeComport("/dev/tty.usbmodem1"), _FakeComport("/dev/tty.usbmodem2")],
        explicit_port="/dev/tty.explicit",
    )

    assert port == "/dev/tty.explicit"


# ---------------------------------------------------------------------------
# parse_args
# ---------------------------------------------------------------------------


def test_parse_args_list_defaults_sd_subpath_to_the_card_root() -> None:
    args = parse_args(["list"])

    assert args.command == "list"
    assert args.sd_subpath == ""


def test_parse_args_list_accepts_an_explicit_subpath() -> None:
    args = parse_args(["list", "aura_packs/scenes"])

    assert args.sd_subpath == "aura_packs/scenes"


def test_parse_args_pull_captures_sd_source_and_host_destination() -> None:
    args = parse_args(["pull", "aura-state.json", "/tmp/aura-state.json"])

    assert args.command == "pull"
    assert args.sd_path == "aura-state.json"
    assert args.host_path == "/tmp/aura-state.json"


def test_parse_args_push_captures_host_source_and_sd_destination() -> None:
    args = parse_args(["push", "/tmp/aura-state.json", "aura-state.json"])

    assert args.command == "push"
    assert args.host_path == "/tmp/aura-state.json"
    assert args.sd_path == "aura-state.json"


def test_parse_args_port_defaults_to_none_for_auto_detect() -> None:
    args = parse_args(["list"])

    assert args.port is None


def test_parse_args_port_override_is_captured() -> None:
    args = parse_args(["pull", "a", "b", "--port", "/dev/tty.usbmodem9"])

    assert args.port == "/dev/tty.usbmodem9"


# ---------------------------------------------------------------------------
# dispatch -- wired to a real SdSyncClient over an in-memory loopback Transport
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


def _loopback_client(storage: "FakeDeviceStorage | None"):
    """Wire a real ``SdSyncClient`` to a fresh ``SdSyncServer(storage)`` over a loopback.

    The server runs on a background daemon thread dispatching by request verb
    (``serve_one``) -- the same shape ``examples/sd_sync.py`` drives on a real
    device, just in-memory -- so ``dispatch`` is exercised end-to-end without
    any real transport or device involved.
    """
    to_server: queue.Queue[bytes] = queue.Queue()
    to_client: queue.Queue[bytes] = queue.Queue()

    client_transport = _QueueTransport(send_q=to_server, recv_q=to_client)
    server_transport = _QueueTransport(send_q=to_client, recv_q=to_server)

    server = SdSyncServer(storage)

    def _serve_forever() -> None:
        while True:
            server.serve_one(server_transport)

    threading.Thread(target=_serve_forever, daemon=True).start()

    return build_client(client_transport)


def test_dispatch_pull_writes_the_sd_file_to_the_given_host_path(tmp_path: Path) -> None:
    storage = FakeDeviceStorage()
    storage.write_bytes("aura-state.json", b'{"scene": "tag"}')
    client = _loopback_client(storage)
    host_path = tmp_path / "aura-state.json"
    args = parse_args(["pull", "aura-state.json", str(host_path)])

    dispatch(args, client)

    assert host_path.read_bytes() == b'{"scene": "tag"}'


def test_dispatch_push_writes_the_host_file_to_the_given_sd_path(tmp_path: Path) -> None:
    storage = FakeDeviceStorage()
    client = _loopback_client(storage)
    host_path = tmp_path / "aura-state.json"
    host_path.write_bytes(b'{"scene": "lobby"}')
    args = parse_args(["push", str(host_path), "aura-state.json"])

    dispatch(args, client)

    assert storage.read_bytes("aura-state.json") == b'{"scene": "lobby"}'


def test_dispatch_list_prints_each_entry_as_tab_separated_path_and_size() -> None:
    storage = FakeDeviceStorage()
    storage.write_bytes("aura-state.json", b'{"scene": "tag"}')
    client = _loopback_client(storage)
    args = parse_args(["list"])
    out = io.StringIO()

    dispatch(args, client, out=out)

    assert out.getvalue() == "aura-state.json\t16\n"


def test_dispatch_returns_zero_on_success() -> None:
    storage = FakeDeviceStorage()
    client = _loopback_client(storage)
    args = parse_args(["list"])

    assert dispatch(args, client, out=io.StringIO()) == 0


def test_dispatch_pull_of_a_missing_sd_path_raises_not_found(tmp_path: Path) -> None:
    client = _loopback_client(FakeDeviceStorage())
    args = parse_args(["pull", "missing.json", str(tmp_path / "missing.json")])

    with pytest.raises(SdSyncNotFoundError):
        dispatch(args, client)

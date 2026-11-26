"""SdSyncServer, the device side of the SD-sync protocol.

Card-less (``storage is None``, i.e. no ``sdcard`` section in ``aura-device.json``)
makes every verb reply ``"no_storage"`` instead of raising (ADR-0011).
"""

from __future__ import annotations

import binascii

from hardware.shared.sd_sync_protocol import (
    CHUNK_SIZE,
    Frame,
    Transport,
    decode_frame,
    encode_frame,
    encode_listing,
    expect_ack,
)

TYPE_CHECKING = False

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from hardware.shared.device_storage import DeviceStorage

__all__ = ["SdSyncServer"]


class _CrcMismatchError(Exception):
    """Internal signal: a push's declared whole-file CRC didn't match the received bytes.

    Raised by :meth:`SdSyncServer._receive_pushed_chunks` inside the iteration
    :meth:`~hardware.shared.device_storage.DeviceStorage.write_chunks` drives,
    aborting that write before its rename (ADR-0011). Caught by
    :meth:`SdSyncServer.serve_push`, never escapes this module.
    """


class _ReplayTransport(Transport):
    """``Transport`` wrapper that replays one already-received line, then delegates.

    :meth:`SdSyncServer.serve_one` must read a request frame to learn its verb
    before it knows which of ``serve_pull``/``serve_push``/``serve_list`` to
    call -- but each of those methods begins by calling ``transport.recv()``
    itself to fetch that same request. Wrapping the real transport in one of
    these lets ``serve_one`` hand off a transport whose first ``recv()`` returns
    the line it already consumed, so the request is serviced once, not lost.
    """

    def __init__(self, inner: Transport, first_line: bytes) -> None:
        self._inner = inner
        self._first_line: bytes | None = first_line

    def send(self, line: bytes) -> None:
        self._inner.send(line)

    def recv(self) -> bytes:
        if self._first_line is not None:
            line, self._first_line = self._first_line, None
            return line
        return self._inner.recv()


class SdSyncServer:
    """Services SD-sync requests against one ``DeviceStorage`` (or none).

    Args:
        storage: The mounted card's storage port, or ``None`` on a device
            whose config declares no ``sdcard`` section.
    """

    def __init__(self, storage: DeviceStorage | None) -> None:
        self._storage = storage

    def _required_storage(self, verb: str) -> DeviceStorage:
        """Return the injected storage, which *verb* cannot run without."""
        storage = self._storage
        assert storage is not None, verb + " needs a server built with storage"
        return storage

    def read(self, sd_path: str) -> Iterator[bytes] | None:
        """Stream *sd_path*'s contents in wire-sized chunks, or ``None`` if never written.

        Read chunk by chunk off disk, never buffered whole (ADR-0011).

        Args:
            sd_path: The file's path, relative to the SD mount root.
        """
        return self._required_storage("read").read_chunks(sd_path, CHUNK_SIZE)

    def write(self, sd_path: str, chunks: Iterable[bytes]) -> None:
        """Durably replace *sd_path* with the streamed *chunks*, creating missing parent dirs.

        Each chunk lands on the sibling temp file as it arrives rather than
        being buffered whole, and the storage layer's atomic-as-FAT-allows
        temp-file-then-rename replace still applies.

        Args:
            sd_path: The file's path, relative to the SD mount root.
            chunks: The file's content, in order.
        """
        self._required_storage("write").write_chunks(sd_path, chunks)

    def list(self, subpath: str = "") -> list[tuple[str, int]] | None:
        """Enumerate every file under *subpath*, or ``None`` if this server has no storage.

        A missing or empty subtree is simply an empty list.

        Args:
            subpath: Mount-relative subtree to enumerate; the default (empty
                string) lists the whole card root.
        """
        if self._storage is None:
            return None
        return self._storage.walk(subpath)

    def serve_pull(self, transport: Transport) -> None:
        """Receive one ``pull`` request on *transport* and serve it to completion.

        Replies ``"no_storage"`` when this server was built with no storage,
        or ``"not_found"`` when *sd_path* was never written. Otherwise replies
        ``"ok"``, streams the file stop-and-wait, and ends with a ``done``
        frame carrying the whole file's CRC-32 (ADR-0011).

        Args:
            transport: The port to receive the request from and reply on.

        Raises:
            ValueError: The client answered a chunk with anything other than
                an ``ack`` of that chunk's sequence number; no further chunks
                are sent.
        """
        request = decode_frame(transport.recv())
        _, _, sd_path = request.text.partition(" ")

        if self._storage is None:
            transport.send(encode_frame(Frame("resp", "no_storage")))
            return

        chunks = self.read(sd_path)
        if chunks is None:
            transport.send(encode_frame(Frame("resp", "not_found")))
            return

        transport.send(encode_frame(Frame("resp", "ok")))

        crc = 0
        for seq, chunk in enumerate(chunks):
            crc = binascii.crc32(chunk, crc)
            transport.send(encode_frame(Frame("chunk", str(seq), chunk)))
            expect_ack(transport, seq)

        transport.send(encode_frame(Frame("done", str(crc))))

    def serve_push(self, transport: Transport) -> None:
        """Receive one ``push`` request on *transport* and serve it to completion.

        Mirrors :meth:`serve_pull` in the opposite direction. Replies
        ``"no_storage"`` when this server was built with no storage,
        otherwise ``"ok"``, then receives the chunks. After the client's
        ``done`` frame it replies ``"ok"`` when the CRC-32 matches (the write
        commits) or ``"crc_mismatch"`` when it doesn't (the card's previous
        content is untouched). See ADR-0011.

        Args:
            transport: The port to receive the request from and reply on.
        """
        request = decode_frame(transport.recv())
        _, _, sd_path = request.text.partition(" ")

        if self._storage is None:
            transport.send(encode_frame(Frame("resp", "no_storage")))
            return

        transport.send(encode_frame(Frame("resp", "ok")))

        try:
            self.write(sd_path, self._receive_pushed_chunks(transport))
        except _CrcMismatchError:
            transport.send(encode_frame(Frame("resp", "crc_mismatch")))
            return

        transport.send(encode_frame(Frame("resp", "ok")))

    def _receive_pushed_chunks(self, transport: Transport) -> Iterator[bytes]:
        """Yield each pushed chunk, acking stop-and-wait, until the closing ``done`` frame.

        Returns, letting the write commit, when the received chunks' CRC-32
        matches the one on ``done``; otherwise raises :class:`_CrcMismatchError`.
        """
        crc = 0
        while True:
            frame = decode_frame(transport.recv())
            if frame.kind != "chunk":
                if crc != int(frame.text):
                    raise _CrcMismatchError
                return
            crc = binascii.crc32(frame.payload, crc)
            transport.send(encode_frame(Frame("ack", frame.text)))
            yield frame.payload

    def serve_list(self, transport: Transport) -> None:
        """Receive one ``list`` request on *transport* and reply with its enumeration.

        Replies ``"no_storage"`` when this server was built with no storage.
        Otherwise replies ``"ok"`` with the enumeration from :meth:`list`
        serialized into the response frame's payload.

        Args:
            transport: The port to receive the request from and reply on.
        """
        request = decode_frame(transport.recv())
        _, _, subpath = request.text.partition(" ")

        entries = self.list(subpath)
        if entries is None:
            transport.send(encode_frame(Frame("resp", "no_storage")))
            return

        transport.send(encode_frame(Frame("resp", "ok", encode_listing(entries))))

    def serve_one(self, transport: Transport) -> None:
        """Receive one request frame and service it, dispatching by its verb.

        Args:
            transport: The port to receive the request from and reply on.

        Raises:
            ValueError: The request's verb is none of ``"pull"``, ``"push"``,
                ``"list"`` -- a malformed request, not a routine outcome -- or
                the serving verb raised it (see :meth:`serve_pull`).
        """
        line = transport.recv()
        verb, _, _ = decode_frame(line).text.partition(" ")
        handlers = {"pull": self.serve_pull, "push": self.serve_push, "list": self.serve_list}
        handler = handlers.get(verb)
        if handler is None:
            raise ValueError(f"unknown SD-sync request verb {verb!r}")
        handler(_ReplayTransport(transport, line))

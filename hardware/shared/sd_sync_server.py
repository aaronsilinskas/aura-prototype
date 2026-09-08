"""SdSyncServer -- the board-free device side of the SD-sync protocol.

Services requests against a :class:`~hardware.shared.device_storage.DeviceStorage`
(the real ``SdCardStorage`` adapter on-device, ``FakeDeviceStorage`` under test),
speaking only the frame vocabulary in :mod:`hardware.shared.sd_sync_protocol`. It
owns no serial code -- ``Transport`` is an injected port, so the same server
logic runs against the real device's data CDC channel or an in-memory loopback
without change.

Two verbs ship so far: ``pull`` (served by :meth:`serve_pull`), which streams a
file's bytes chunk-by-chunk with a whole-file CRC-32 for the client to verify,
and ``list`` (served by :meth:`serve_list`), which enumerates a subtree via
``DeviceStorage.walk`` and replies with the whole listing in one frame. ``push``
is a later verb.

Card-less (``storage is None``, i.e. no ``sdcard`` section in ``aura-device.json``)
makes every verb reply with a clear ``"no_storage"`` response instead of raising
-- a request for a file is a normal, expected event on a card-less device, not a
programming error.

No ``board``/``busio``/CircuitPython-only import -- safe on CPython,
CircuitPython 10.x, and MicroPython.
"""

from __future__ import annotations

import binascii

try:
    from collections.abc import Iterator
except ImportError:
    pass  # Not available on all embedded runtimes

from hardware.shared.device_storage import DeviceStorage
from hardware.shared.sd_sync_protocol import (
    CHUNK_SIZE,
    Frame,
    Transport,
    decode_frame,
    encode_frame,
    encode_listing,
)

__all__ = ["SdSyncServer"]


class SdSyncServer:
    """Services SD-sync requests against one ``DeviceStorage`` (or none).

    Args:
        storage: The mounted card's storage port, or ``None`` on a device
            whose config declares no ``sdcard`` section.
    """

    def __init__(self, storage: DeviceStorage | None) -> None:
        self._storage = storage

    def read(self, sd_path: str) -> Iterator[bytes] | None:
        """Stream *sd_path*'s contents in wire-sized chunks, or ``None`` if never written.

        A thin read through the injected storage's
        :meth:`~hardware.shared.device_storage.DeviceStorage.read_chunks` --
        the file is read chunk-by-chunk off disk, never buffered whole, so
        transfer memory is bounded by one chunk rather than by the file (see
        the parent spec's bounded-memory contract). :meth:`serve_pull` is what
        turns the chunks into acknowledged wire frames -- this method exists
        as its own seam so a caller (or a future verb) can reuse the
        streaming read without going through the wire protocol.

        Args:
            sd_path: The file's path, relative to the SD mount root.
        """
        return self._storage.read_chunks(sd_path, CHUNK_SIZE)

    def list(self, subpath: str = "") -> list[tuple[str, int]] | None:
        """Enumerate every file under *subpath*, or ``None`` if this server has no storage.

        A thin read through the injected storage's
        :meth:`~hardware.shared.device_storage.DeviceStorage.walk`. Unlike
        :meth:`read`, there is no per-path "not found" case here -- a missing
        or empty subtree is simply an empty list; ``None`` means only "this
        server was built with no storage," mirroring how ``storage is None``
        replies ``"no_storage"`` on the wire instead of raising.

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
        or ``"not_found"`` when *sd_path* was never written -- both clear,
        in-band responses rather than a raised exception, since either is a
        routine outcome from the client's perspective. Otherwise replies
        ``"ok"``, then streams the file as a sequence of
        :data:`~hardware.shared.sd_sync_protocol.CHUNK_SIZE`-bounded chunks
        read straight off disk by :meth:`read`, waiting for the client's
        ``ack`` before sending the next (stop-and-wait), and finishes with a
        ``done`` frame carrying the whole file's incremental CRC-32 for the
        client to verify.

        Args:
            transport: The port to receive the request from and reply on.
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
            transport.recv()  # ack -- stop-and-wait; the seq is implied by order

        transport.send(encode_frame(Frame("done", str(crc))))

    def serve_list(self, transport: Transport) -> None:
        """Receive one ``list`` request on *transport* and reply with its enumeration.

        Replies ``"no_storage"`` when this server was built with no storage
        -- the same in-band response :meth:`serve_pull` uses instead of
        raising, since a listing request against a card-less device is
        routine. Otherwise replies ``"ok"`` with the enumeration from
        :meth:`list` serialized into the response frame's payload via
        :func:`~hardware.shared.sd_sync_protocol.encode_listing`.

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

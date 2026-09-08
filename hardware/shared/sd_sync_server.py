"""SdSyncServer -- the board-free device side of the SD-sync protocol.

Services requests against a :class:`~hardware.shared.device_storage.DeviceStorage`
(the real ``SdCardStorage`` adapter on-device, ``FakeDeviceStorage`` under test),
speaking only the frame vocabulary in :mod:`hardware.shared.sd_sync_protocol`. It
owns no serial code -- ``Transport`` is an injected port, so the same server
logic runs against the real device's data CDC channel or an in-memory loopback
without change.

This ticket builds the first verb, ``pull`` (served by :meth:`serve_pull`), plus
the streaming/CRC machinery every later verb (``list``, ``push``) will reuse.

Card-less (``storage is None``, i.e. no ``sdcard`` section in ``aura-device.json``)
makes every verb reply with a clear ``"no_storage"`` response instead of raising
-- a request for a file is a normal, expected event on a card-less device, not a
programming error.

No ``board``/``busio``/CircuitPython-only import -- safe on CPython,
CircuitPython 10.x, and MicroPython.
"""

from __future__ import annotations

import binascii

from hardware.shared.device_storage import DeviceStorage
from hardware.shared.sd_sync_protocol import (
    Frame,
    Transport,
    decode_frame,
    encode_frame,
    iter_chunks,
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

    def read(self, sd_path: str) -> bytes | None:
        """Return *sd_path*'s full contents, or ``None`` if it was never written.

        A thin read through the injected storage; :meth:`serve_pull` is what
        turns the result into bounded, acknowledged wire chunks -- this method
        exists as its own seam so a caller (or a future verb) can reuse the
        read without going through the wire protocol.

        Args:
            sd_path: The file's path, relative to the SD mount root.
        """
        return self._storage.read_bytes(sd_path)

    def serve_pull(self, transport: Transport) -> None:
        """Receive one ``pull`` request on *transport* and serve it to completion.

        Replies ``"no_storage"`` when this server was built with no storage,
        or ``"not_found"`` when *sd_path* was never written -- both clear,
        in-band responses rather than a raised exception, since either is a
        routine outcome from the client's perspective. Otherwise replies
        ``"ok"`` with the file size, then streams the file as a sequence of
        :data:`~hardware.shared.sd_sync_protocol.CHUNK_SIZE`-bounded chunks,
        waiting for the client's ``ack`` before sending the next (stop-and-
        wait), and finishes with a ``done`` frame carrying the whole file's
        incremental CRC-32 for the client to verify.

        Args:
            transport: The port to receive the request from and reply on.
        """
        request = decode_frame(transport.recv())
        _, _, sd_path = request.text.partition(" ")

        if self._storage is None:
            transport.send(encode_frame(Frame("resp", "no_storage")))
            return

        data = self.read(sd_path)
        if data is None:
            transport.send(encode_frame(Frame("resp", "not_found")))
            return

        transport.send(encode_frame(Frame("resp", f"ok {len(data)}")))

        crc = 0
        for seq, chunk in enumerate(iter_chunks(data)):
            crc = binascii.crc32(chunk, crc)
            transport.send(encode_frame(Frame("chunk", str(seq), chunk)))
            transport.recv()  # ack -- stop-and-wait; the seq is implied by order

        transport.send(encode_frame(Frame("done", str(crc))))

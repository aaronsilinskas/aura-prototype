"""SdSyncClient -- the host side of the SD-sync protocol.

Drives an :class:`~hardware.shared.sd_sync_server.SdSyncServer` (over an
injected :class:`~hardware.shared.sd_sync_protocol.Transport`) to pull files off
a device's SD card onto the host filesystem. CPython-only, like the rest of
``scripts/``; the real serial transport (pointed at the device's data CDC port)
is a later ticket -- this client only knows the ``Transport`` port, so it runs
unchanged against that transport or an in-memory loopback.

Each ``pull`` writes the received bytes to the host path chunk-by-chunk as they
arrive, so the host process never holds a whole file in memory either -- the
same bounded-memory contract :class:`SdSyncServer` keeps on the device side.

The whole-file CRC-32 the server sends after the last chunk is compared against
one accumulated the same way, chunk-by-chunk, while writing. A mismatch retries
the whole pull from scratch (a fresh request, a fresh receive) up to
``max_attempts`` times; exhausting them raises :class:`SdSyncIntegrityError`
rather than leaving a corrupt file with no indication anything went wrong.
"""

import binascii
import os
from typing import Final

from hardware.shared.sd_sync_protocol import Frame, Transport, decode_frame, encode_frame

__all__ = [
    "SdSyncClient",
    "SdSyncError",
    "SdSyncIntegrityError",
    "SdSyncNoStorageError",
    "SdSyncNotFoundError",
]

DEFAULT_MAX_ATTEMPTS: Final = 3


class SdSyncError(Exception):
    """Base for every error :class:`SdSyncClient` raises."""


class SdSyncNoStorageError(SdSyncError):
    """The device has no SD card configured (no ``sdcard`` section)."""


class SdSyncNotFoundError(SdSyncError):
    """The requested SD path was never written."""


class SdSyncIntegrityError(SdSyncError):
    """Every retry attempt's CRC-32 mismatched; the transfer could not be verified."""


class SdSyncClient:
    """Pulls files from a device's SD card over an injected ``Transport``.

    Args:
        transport: The port to reach the server through (real serial, or an
            in-memory loopback for tests).
        max_attempts: Total attempts (initial try plus retries) before a
            checksum-verified pull gives up and raises
            :class:`SdSyncIntegrityError`.
    """

    def __init__(self, transport: Transport, max_attempts: int = DEFAULT_MAX_ATTEMPTS) -> None:
        self._transport = transport
        self._max_attempts = max_attempts

    def pull(self, sd_path: str, host_path: str) -> None:
        """Download *sd_path* from the SD card to *host_path*, preserving its bytes exactly.

        Creates any missing parent directories under *host_path* so a pull
        into a not-yet-existing host subtree works. Nothing is written to
        *host_path* unless the server confirms the file exists, so a "not
        found" pull leaves no empty file behind.

        Args:
            sd_path: The file's path, relative to the SD mount root.
            host_path: Where to write the file on the host filesystem.

        Raises:
            SdSyncNoStorageError: The device has no SD card configured.
            SdSyncNotFoundError: *sd_path* was never written on the SD card.
            SdSyncIntegrityError: Every attempt's CRC-32 mismatched.
        """
        for _attempt in range(self._max_attempts):
            self._transport.send(encode_frame(Frame("req", f"pull {sd_path}")))
            response = decode_frame(self._transport.recv())
            status, _, _ = response.text.partition(" ")

            if status == "no_storage":
                raise SdSyncNoStorageError(f"no SD configured; cannot pull {sd_path!r}")
            if status == "not_found":
                raise SdSyncNotFoundError(f"{sd_path!r} not found on SD card")

            if self._receive_verified(host_path):
                return

        _remove_if_exists(host_path)
        raise SdSyncIntegrityError(
            f"CRC-32 mismatch pulling {sd_path!r} after {self._max_attempts} attempt(s)"
        )

    def _receive_verified(self, host_path: str) -> bool:
        """Stream one pull response's chunks to *host_path*; return whether its CRC matched.

        Runs after the server has already confirmed ``"ok"`` -- acknowledges
        each chunk (stop-and-wait) and writes it immediately, so *host_path*
        never holds more than one pending chunk in memory before it lands on
        disk.
        """
        parent = os.path.dirname(host_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        crc = 0
        with open(host_path, "wb") as host_file:
            while True:
                frame = decode_frame(self._transport.recv())
                if frame.kind == "chunk":
                    crc = binascii.crc32(frame.payload, crc)
                    host_file.write(frame.payload)
                    self._transport.send(encode_frame(Frame("ack", frame.text)))
                else:  # "done"
                    server_crc = int(frame.text)
                    break

        return crc == server_crc


def _remove_if_exists(host_path: str) -> None:
    """Remove *host_path* if present -- leaves no partial file after exhausted retries."""
    try:
        os.remove(host_path)
    except FileNotFoundError:
        pass

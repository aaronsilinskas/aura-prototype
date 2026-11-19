"""SdSyncClient -- the host side of the SD-sync protocol.

Drives an :class:`~hardware.shared.sd_sync_server.SdSyncServer` (over an
injected :class:`~hardware.shared.sd_sync_protocol.Transport`) to pull files off
a device's SD card onto the host filesystem, push host files onto the card, and
list directories on the card. CPython-only, like the rest of ``scripts/``; the
real serial transport (:class:`~scripts.sd_sync_transport.SerialTransport`, on the
device's data channel) is one implementation -- this client only knows the
``Transport`` port, so it runs unchanged against that transport or an in-memory
loopback.

Each ``pull``/``push`` streams chunk by chunk and is checked by a whole-file
CRC-32; a mismatch retries the whole transfer up to ``max_attempts`` times, then
raises :class:`SdSyncIntegrityError`. See ADR-0011.
"""

import binascii
import os
import secrets
from typing import BinaryIO, Final

from hardware.shared.sd_sync_protocol import (
    CHUNK_SIZE,
    Frame,
    Transport,
    decode_frame,
    decode_listing,
    encode_frame,
)

__all__ = [
    "SdSyncClient",
    "SdSyncError",
    "SdSyncIntegrityError",
    "SdSyncNoStorageError",
    "SdSyncNotFoundError",
    "SdSyncProtocolError",
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


class SdSyncProtocolError(SdSyncError, ValueError):
    """The server broke the protocol, so the exchange cannot safely continue.

    Also a ``ValueError``, the type :class:`SdSyncServer` raises when the client
    breaks the protocol.
    """


class SdSyncClient:
    """Pulls files from, and pushes files to, a device's SD card over an injected ``Transport``.

    Args:
        transport: The port to reach the server through.
        max_attempts: Total attempts (initial try plus retries) before a
            checksum-verified pull or push gives up and raises
            :class:`SdSyncIntegrityError`.
    """

    def __init__(self, transport: Transport, max_attempts: int = DEFAULT_MAX_ATTEMPTS) -> None:
        self._transport = transport
        self._max_attempts = max_attempts

    def pull(self, sd_path: str, host_path: str) -> None:
        """Download *sd_path* from the SD card to *host_path*, preserving its bytes exactly.

        Creates any missing parent directories under *host_path* so a pull
        into a not-yet-existing host subtree works. *host_path* is replaced
        only once a transfer's CRC-32 matches: a pull that raises (Ctrl-C
        included) leaves an existing *host_path* unchanged and no partial file
        behind.

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

        raise SdSyncIntegrityError(
            f"CRC-32 mismatch pulling {sd_path!r} after {self._max_attempts} attempt(s)"
        )

    def list_files(self, sd_subpath: str = "") -> list[tuple[str, int]]:
        """Return the server's enumeration of *sd_subpath* on the SD card.

        Args:
            sd_subpath: Mount-relative subtree to enumerate; the default
                (empty string) lists the whole card root.

        Raises:
            SdSyncNoStorageError: The device has no SD card configured.
        """
        self._transport.send(encode_frame(Frame("req", f"list {sd_subpath}")))
        response = decode_frame(self._transport.recv())
        status, _, _ = response.text.partition(" ")

        if status == "no_storage":
            raise SdSyncNoStorageError(f"no SD configured; cannot list {sd_subpath!r}")

        return decode_listing(response.payload)

    def _receive_verified(self, host_path: str) -> bool:
        """Receive one pull response into *host_path*; return whether its CRC matched."""
        parent = os.path.dirname(host_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        # Beside host_path so os.replace stays on one filesystem and is atomic;
        # opened like a normal file (not tempfile's 0600) so the result gets
        # the umask's usual permissions.
        temp_path = f"{host_path}.{secrets.token_hex(8)}.part"
        try:
            with open(temp_path, "xb") as temp_file:
                crc_matched = self._receive_chunks(temp_file)
            if crc_matched:
                os.replace(temp_path, host_path)
            return crc_matched
        finally:
            _remove_if_exists(temp_path)

    def _receive_chunks(self, dest: BinaryIO) -> bool:
        """Write and ack each chunk to *dest* as it arrives; return whether the CRC matched."""
        crc = 0
        while True:
            frame = decode_frame(self._transport.recv())
            if frame.kind == "chunk":
                crc = binascii.crc32(frame.payload, crc)
                dest.write(frame.payload)
                self._transport.send(encode_frame(Frame("ack", frame.text)))
            else:  # "done"
                return crc == int(frame.text)

    def push(self, host_path: str, sd_path: str) -> None:
        """Upload *host_path* to the SD card at *sd_path*, preserving its bytes exactly.

        Reads the host file chunk-by-chunk, never buffering the whole file. A
        CRC-32 mismatch retries the whole upload up to ``max_attempts`` times.

        Args:
            host_path: The local file to upload.
            sd_path: Where to write it on the SD card, relative to the mount
                root -- preserved exactly, independent of *host_path*'s own
                layout.

        Raises:
            SdSyncNoStorageError: The device has no SD card configured.
            SdSyncIntegrityError: Every attempt's CRC-32 mismatched.
            SdSyncProtocolError: The server replied to a chunk with anything
                but that chunk's ack; the push stops without retrying.
        """
        for _attempt in range(self._max_attempts):
            self._transport.send(encode_frame(Frame("req", f"push {sd_path}")))
            response = decode_frame(self._transport.recv())
            status, _, _ = response.text.partition(" ")

            if status == "no_storage":
                raise SdSyncNoStorageError(f"no SD configured; cannot push to {sd_path!r}")

            if self._send_verified(host_path):
                return

        raise SdSyncIntegrityError(
            f"CRC-32 mismatch pushing {host_path!r} to {sd_path!r} after "
            f"{self._max_attempts} attempt(s)"
        )

    def _send_verified(self, host_path: str) -> bool:
        """Stream *host_path* to the server (stop-and-wait); return whether it committed.

        Runs after the server has already confirmed ``"ok"`` for the request.
        The server replies to the
        closing ``done`` frame with ``"ok"`` (committed) or ``"crc_mismatch"``
        (left on disk untouched).

        Raises:
            SdSyncProtocolError: A chunk's reply was not the ack carrying its
                sequence number.
        """
        crc = 0
        with open(host_path, "rb") as host_file:
            seq = 0
            while True:
                chunk = host_file.read(CHUNK_SIZE)
                if not chunk:
                    break
                crc = binascii.crc32(chunk, crc)
                self._transport.send(encode_frame(Frame("chunk", str(seq), chunk)))
                self._expect_ack(seq)
                seq += 1

        self._transport.send(encode_frame(Frame("done", str(crc))))
        response = decode_frame(self._transport.recv())
        return response.text == "ok"

    def _expect_ack(self, seq: int) -> None:
        """Consume chunk *seq*'s ack, refusing to stream past any other reply.

        Raises:
            SdSyncProtocolError: The reply was not ``ack`` carrying *seq*.
        """
        frame = decode_frame(self._transport.recv())
        if frame.kind != "ack" or frame.text != str(seq):
            raise SdSyncProtocolError(
                f"expected SD-sync frame 'ack' {str(seq)!r}, got {frame.kind!r} {frame.text!r}"
            )


def _remove_if_exists(path: str) -> None:
    """Remove *path* if it exists."""
    try:
        os.remove(path)
    except FileNotFoundError:
        pass

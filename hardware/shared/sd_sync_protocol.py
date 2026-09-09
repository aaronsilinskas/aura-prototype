"""SD-sync wire protocol — board-free frame representation shared by client and server.

Every request, response, and streamed file chunk is carried as one **frame**: a
small ASCII header line (``kind`` plus a free-form ``text`` field) optionally
followed by raw payload bytes, the whole thing base64-encoded as a single unit.
Base64 keeps every frame plain-ASCII and line-safe -- no embedded newline or
control byte can desync a line-oriented reader -- and carries an arbitrary
binary payload (a file chunk) intact, since base64 has no notion of "binary"
versus "text" content.

``Transport`` is the port both :class:`hardware.shared.sd_sync_server.SdSyncServer`
and ``scripts.sd_sync_client.SdSyncClient`` reach each other through --
``send``/``recv`` of one already-encoded frame line at a time. The real serial
adapter (a later ticket) and the in-memory loopback used by tests are both thin
implementations of this port; neither this module nor its callers know or care
which one is underneath.

``CHUNK_SIZE`` bounds how much of a file is ever in flight as a single frame:
:func:`iter_chunks` slices a bytes object into pieces of at most this size, so a
sender streams a file chunk-by-chunk rather than as one frame, and a receiver
never has to hold more than one chunk's worth of un-acknowledged data.

No ``board``/``busio``/CircuitPython-only import -- safe on CPython,
CircuitPython 10.x, and MicroPython.
"""

import binascii

try:
    from collections.abc import Iterator
    from typing import Final
except ImportError:
    pass  # Not available on all embedded runtimes

__all__ = [
    "CHUNK_SIZE",
    "Frame",
    "Transport",
    "decode_frame",
    "decode_listing",
    "encode_frame",
    "encode_listing",
    "iter_chunks",
]

CHUNK_SIZE: Final = 512


class Frame:
    """One decoded protocol frame: a ``kind``, a free-form ``text``, and raw ``payload`` bytes.

    A plain value holder (no ``dataclasses`` -- unavailable on constrained
    runtimes). ``kind`` names the frame's role (``"req"``, ``"resp"``,
    ``"chunk"``, ``"ack"``, ``"done"``); ``text`` carries whatever small
    fields that kind needs (e.g. a request's ``"pull aura-state.json"``, a
    chunk's sequence number) as a single string callers split themselves;
    ``payload`` carries the raw bytes for kinds that move file content
    (empty for every other kind).
    """

    __slots__ = ("kind", "payload", "text")

    def __init__(self, kind: str, text: str = "", payload: bytes = b"") -> None:
        self.kind = kind
        self.text = text
        self.payload = payload


class Transport:
    """Port through which the SD-sync client and server exchange encoded frame lines.

    A plain base class -- the same substitute pattern as ``RadioTransport``
    and ``PulseReader``/``PulseWriter`` (``typing.Protocol`` is unavailable on
    the constrained runtimes). Subclass and override both methods to connect
    to a real serial link or an in-memory test double.
    """

    def send(self, line: bytes) -> None:
        """Send one already-encoded frame line.

        Raises:
            NotImplementedError: Always -- subclasses must override.
        """
        raise NotImplementedError

    def recv(self) -> bytes:
        """Block until the next frame line arrives and return it.

        Raises:
            NotImplementedError: Always -- subclasses must override.
        """
        raise NotImplementedError


def encode_frame(frame: Frame) -> bytes:
    """Encode *frame* as a single base64 line -- plain-ASCII, no embedded newlines.

    The header (``kind`` + a space + ``text``) and ``payload`` are joined with
    a single ``\\n`` separator before base64 encoding; that inner newline is
    swallowed by the encoding, so the returned bytes contain none.
    """
    header = (frame.kind + " " + frame.text).encode("utf-8")
    # binascii.b2a_base64 always appends a trailing newline; strip it so the
    # returned bytes stay a single line with none embedded.
    return binascii.b2a_base64(header + b"\n" + frame.payload).rstrip(b"\n")


def decode_frame(line: bytes) -> Frame:
    """Decode a base64 *line* produced by :func:`encode_frame` back into a ``Frame``."""
    raw = binascii.a2b_base64(line)
    header, _, payload = raw.partition(b"\n")
    kind, _, text = header.decode("utf-8").partition(" ")
    return Frame(kind, text, payload)


def encode_listing(entries: "list[tuple[str, int]]") -> bytes:
    """Serialize (path, size) pairs into a ``list`` response frame's payload.

    One ``"path\\tsize"`` line per entry, newline-joined, UTF-8 encoded --
    a listing is small enough (unlike a pulled file's contents) to send
    whole in a single frame rather than chunked. A free implementation
    detail of the ``list`` verb, paired with :func:`decode_listing`; not
    asserted directly by tests, only through the round trip it enables.
    """
    return "\n".join(f"{path}\t{size}" for path, size in entries).encode("utf-8")


def decode_listing(payload: bytes) -> "list[tuple[str, int]]":
    """Parse a payload produced by :func:`encode_listing` back into (path, size) pairs.

    Empty *payload* decodes to an empty list, matching an empty or
    missing subtree.
    """
    if not payload:
        return []
    entries: list[tuple[str, int]] = []
    for line in payload.decode("utf-8").split("\n"):
        path, _, size = line.partition("\t")
        entries.append((path, int(size)))
    return entries


def iter_chunks(data: bytes, chunk_size: int = CHUNK_SIZE) -> "Iterator[bytes]":
    """Yield *data* sliced into pieces of at most *chunk_size* bytes.

    Slicing ``bytes`` copies the slice but never the parts already yielded and
    discarded by the caller, so a streaming sender holds at most one chunk
    plus the source bytes -- not a second full copy -- at any time. Yields
    nothing for empty *data* (an empty file has zero chunks, not one empty
    chunk); the CRC-32 of zero chunks is correctly the identity value ``0``.
    """
    for start in range(0, len(data), chunk_size):
        yield data[start : start + chunk_size]

# SD sync is a stop-and-wait line protocol on the data channel, checked by a whole-file CRC-32

The host reaches the SD card through a serial protocol on the **Data channel**, the second USB-CDC channel `boot.py` enables, never on the **Console channel**. Every request, response and file chunk is one frame: a `kind text` header and an optional payload, base64-encoded as a single newline-terminated line. A file moves as chunks of at most `CHUNK_SIZE` bytes (512). The receiver acknowledges each chunk with an `ack` carrying its sequence number before the sender sends the next. The closing `done` frame carries the CRC-32 of the whole file, accumulated chunk by chunk. A mismatch makes `SdSyncClient` rerun the whole transfer, a fresh request and a fresh read, up to three attempts, and then raise `SdSyncIntegrityError`. The firmware's `SdSyncServer` and the host's `SdSyncClient` both depend on this, so a change ships to both at once.

Spec #925 chose this because the SD card sits on the device's SPI bus and is not host-mountable, so editing `aura-state.json` or card content meant pulling the card. The spec fixed base64 line framing, streamed stop-and-wait, bounded memory and an incremental CRC-32 as the contract. Frame grammar, chunk size, ack shape and retry count were left as implementation details.

- **A separate channel.** Console output (logs, tracebacks, the reboot banner) and file frames never share a stream, so neither corrupts the other.
- **Base64 lines.** No newline, `Ctrl-C`/`Ctrl-D` or control byte can desync a line reader, and binary files (`.wav`, logs) move intact.
- **Stop-and-wait, streamed on both sides.** The sender never overruns the device's read buffer. Each side reads or writes the open file one chunk at a time, so transfer memory is bounded by a chunk, not by the file, which matters for files larger than the device's free RAM.
- **One CRC-32 per file.** USB CDC bulk transfers are already error-checked and retransmitted by USB, so the remaining risk is at the application layer (framing, a stray frame). `binascii.crc32` can be fed chunk by chunk and is available on the device.

## Considered Options

- **Expose the card as USB Mass Storage.** Rejected: CircuitPython fixes whether a volume is a host drive in `boot.py`, a running script can't switch it back, and while the host holds it the volume is read-only to device code.
- **A boot-time flash inbox (#916).** Rejected: it can't read from the card, and it is one-directional and boot-gated.
- **SHA-256.** Rejected as heavier, and `hashlib` may be missing from a constrained build.
- **A CRC per chunk with resume, or a sliding window.** Spec #925 doesn't weigh these. The likely reasons, to be confirmed: transfers are bench-sized, so rerunning a whole file is cheap, and a window would need the device to buffer several unacknowledged chunks, giving up the one-chunk memory bound.

## Consequences

- A failed push never replaces the file on the card. `SdSyncServer` checks the CRC while `DeviceStorage.write_chunks` is still consuming the chunks, and a mismatch aborts the write before its rename. A pull whose retries all fail the CRC leaves no partial host file. A pull stopped by a transport or protocol error can, because the client writes straight to the host path, truncating any file already there.
- On pull, the server checks each ack: anything but an `ack` of the sequence number just sent raises `ValueError`, and no further chunk is sent (#1438). On push, the server echoes each chunk's sequence number in its ack. The client waits for that ack before sending the next chunk, but doesn't decode or check it: the whole-file CRC is the only check on a push.
- A listing is small, so it travels whole in one response frame, with no chunking and no CRC.
- "Not found" and "no SD configured" are in-band responses, not errors on the device, because both are routine for a bench tool.

"""CountingI2C — a ``busio.I2C`` decorator that tallies byte traffic."""

from __future__ import annotations

import busio


def _slice_len(buffer: bytearray, start: int, end: int | None) -> int:
    """Byte count of a ``[start:end]`` slice; ``end=None`` means end of *buffer*."""
    return (end if end is not None else len(buffer)) - start


class CountingI2C:
    """Transparent decorator around a ``busio.I2C`` bus that counts transferred bytes.

    Forwards the full ``adafruit_bus_device.I2CDevice`` surface.
    Lock/scan/deinit calls do not affect counters.

    The full ``busio.I2C`` surface is intentional and load-bearing: a prior
    version missing the ``scan``/``probe`` forwards deadlocked matrix init.
    Do not narrow this surface without re-verifying that path.
    """

    def __init__(self, inner: busio.I2C) -> None:
        self._inner = inner
        self.bytes_written: int = 0
        self.bytes_read: int = 0

    def reset(self) -> None:
        self.bytes_written = 0
        self.bytes_read = 0

    def try_lock(self) -> bool:
        return self._inner.try_lock()

    def unlock(self) -> None:
        self._inner.unlock()

    def writeto(
        self, address: int, buffer: bytearray, *, start: int = 0, end: int | None = None
    ) -> None:
        resolved_end = end if end is not None else len(buffer)
        self.bytes_written += _slice_len(buffer, start, end)
        self._inner.writeto(address, buffer, start=start, end=resolved_end)

    def readfrom_into(
        self, address: int, buffer: bytearray, *, start: int = 0, end: int | None = None
    ) -> None:
        resolved_end = end if end is not None else len(buffer)
        self.bytes_read += _slice_len(buffer, start, end)
        self._inner.readfrom_into(address, buffer, start=start, end=resolved_end)

    def writeto_then_readfrom(
        self,
        address: int,
        out_buffer: bytearray,
        in_buffer: bytearray,
        *,
        out_start: int = 0,
        out_end: int | None = None,
        in_start: int = 0,
        in_end: int | None = None,
    ) -> None:
        resolved_out_end = out_end if out_end is not None else len(out_buffer)
        resolved_in_end = in_end if in_end is not None else len(in_buffer)
        self.bytes_written += _slice_len(out_buffer, out_start, out_end)
        self.bytes_read += _slice_len(in_buffer, in_start, in_end)
        self._inner.writeto_then_readfrom(
            address,
            out_buffer,
            in_buffer,
            out_start=out_start,
            out_end=resolved_out_end,
            in_start=in_start,
            in_end=resolved_in_end,
        )

    def scan(self) -> list[int]:
        return self._inner.scan()

    def probe(self, address: int) -> bool:
        return self._inner.probe(address)  # type: ignore[return-value]  # stub incorrectly declares List[int]; C source returns bool

    def deinit(self) -> None:
        self._inner.deinit()

    def __del__(self) -> None:
        self._inner.deinit()

    def __enter__(self) -> CountingI2C:
        self._inner.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        self._inner.__exit__(exc_type, exc_val, exc_tb)  # type: ignore

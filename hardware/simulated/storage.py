"""An in-memory ``DeviceStorage`` double for the ``hardware/shared`` storage tests.

It stays a faithful copy of ``DeviceStorage``'s contract.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from hardware.shared.device_storage import (
    DeviceStorage,
    decode_json,
    encode_json,
    reject_escaping_path,
)

__all__ = ["FakeDeviceStorage"]


class FakeDeviceStorage(DeviceStorage):
    """In-memory ``DeviceStorage`` modelling its observable contract.

    A subclass only so it stands wherever a ``DeviceStorage`` is expected:
    ``DeviceStorage`` is itself the filesystem adapter (there is no separate
    abstract port, unlike ``RadioTransport``/``PulseWriter``), so every public
    method is overridden against a plain dict and none of the filesystem
    behaviour is used.
    """

    _MOUNT_ROOT = "/fake-mount"

    def __init__(self) -> None:
        super().__init__(self._MOUNT_ROOT)
        self._files: dict[str, bytes] = {}

    def read_bytes(self, name: str) -> bytes | None:
        self._guard(name)
        return self._files.get(name)

    def read_chunks(self, name: str, chunk_size: int) -> Iterator[bytes] | None:
        self._guard(name)
        data = self._files.get(name)
        if data is None:
            return None
        return (data[start : start + chunk_size] for start in range(0, len(data), chunk_size))

    def write_bytes(self, name: str, data: bytes) -> None:
        self._guard(name)
        self._files[name] = bytes(data)

    def write_chunks(self, name: str, chunks: Iterable[bytes]) -> None:
        self._guard(name)
        self._files[name] = b"".join(chunks)

    def read_json(self, name: str) -> dict | None:
        data = self.read_bytes(name)
        if data is None:
            return None
        return decode_json(data)

    def write_json(self, name: str, mapping: dict) -> None:
        self.write_bytes(name, encode_json(mapping))

    def path(self, subpath: str) -> str:
        self._guard(subpath)
        return self._MOUNT_ROOT + "/" + subpath

    def walk(self, subpath: str = "") -> list[tuple[str, int]]:
        """Mirror ``DeviceStorage.walk`` against the flat ``_files`` dict.

        There is no directory modelling here -- each key in ``_files`` is
        already the full mount-relative path a real ``DeviceStorage`` would
        report, so scoping to *subpath* is a prefix filter rather than a
        recursive descent.
        """
        self._guard(subpath)
        prefix = subpath.rstrip("/")
        entries: list[tuple[str, int]] = []
        for name, data in self._files.items():
            if prefix and name != prefix and not name.startswith(prefix + "/"):
                continue
            entries.append((name, len(data)))
        entries.sort()
        return entries

    def _guard(self, relative_path: str) -> None:
        reject_escaping_path(relative_path)

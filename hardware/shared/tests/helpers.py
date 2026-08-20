"""Shared test doubles for hardware/shared, importable across test modules."""

import json

from hardware.shared.device_storage import reject_escaping_path

__all__ = ["FakeDeviceStorage"]


class FakeDeviceStorage:
    """In-memory ``DeviceStorage`` double modelling its observable contract.

    Not a subclass of :class:`hardware.shared.device_storage.DeviceStorage`
    -- that class is a concrete, directly-instantiable filesystem adapter
    (there is no separate abstract port to share, unlike
    ``RadioTransport``/``PulseWriter``), so this fake reimplements the same
    accessor surface against a plain dict rather than inheriting filesystem
    behaviour it would only have to override.
    """

    _MOUNT_ROOT = "/fake-mount"

    def __init__(self) -> None:
        self._files: dict[str, bytes] = {}

    @property
    def mount_root(self) -> str:
        return self._MOUNT_ROOT

    def read_bytes(self, name: str) -> "bytes | None":
        self._guard(name)
        return self._files.get(name)

    def write_bytes(self, name: str, data: bytes) -> None:
        self._guard(name)
        self._files[name] = bytes(data)

    def read_json(self, name: str) -> "dict | None":
        data = self.read_bytes(name)
        if data is None:
            return None
        return json.loads(data.decode("utf-8"))

    def write_json(self, name: str, mapping: dict) -> None:
        self.write_bytes(name, json.dumps(mapping).encode("utf-8"))

    def path(self, subpath: str) -> str:
        self._guard(subpath)
        return self._MOUNT_ROOT + "/" + subpath

    def _guard(self, relative_path: str) -> None:
        reject_escaping_path(relative_path)

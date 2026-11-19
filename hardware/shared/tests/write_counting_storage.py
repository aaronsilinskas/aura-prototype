"""A real ``DeviceStorage`` that counts ``write_json`` calls, so a test can see writes land."""

from hardware.shared.device_storage import DeviceStorage


class WriteCountingStorage(DeviceStorage):
    def __init__(self, mount_root: str) -> None:
        super().__init__(mount_root)
        self.json_writes = 0

    def write_json(self, name: str, mapping: dict) -> None:
        self.json_writes += 1
        super().write_json(name, mapping)

"""DeviceStateStore -- owns aura-state.json, the device-written SD state file.

Persists small key/value state a device writes about itself (today: the
Persisted scene, its return_to companion, and the last applied Scene deploy
token) across a reboot. Built
entirely on the DeviceStorage port's read_json/write_json convenience, so
this module has no board/sdcardio/storage import and is CPython-testable
like the rest of hardware/shared -- the live adapter is whatever DeviceStorage
implementation DeviceHardware.storage holds (None on a card-less device).
"""

from __future__ import annotations

import json

from engine.log import Logger
from hardware.shared.device_storage import DeviceStorage

__all__ = ["DeviceStateStore"]

_STATE_FILE_NAME = "aura-state.json"


class DeviceStateStore:
    """Read/write access to aura-state.json's flat string -> value mapping.

    Args:
        storage: The mounted DeviceStorage to persist through, or None on a
            device with no sdcard section configured -- every read then
            reports empty state and every write is a silent no-op.
        logger: Where a fail-soft read (malformed or non-object file
            content) is logged. Omitted or None normalizes to
            Logger.SILENT, matching the rest of hardware/shared.
    """

    def __init__(self, storage: DeviceStorage | None, logger: Logger | None = None) -> None:
        self._storage = storage
        self._logger = logger if logger is not None else Logger.SILENT

    def get(self, key: str) -> str | None:
        """Return *key*'s persisted value, or None if it was never set.

        Never-written file, malformed JSON, non-object JSON, and a missing
        *key* within an otherwise-valid object all report the same absent
        result -- an unset key is an ordinary case, not an error.
        """
        return self.read().get(key)

    def read(self) -> dict:
        """Return the whole persisted mapping, empty when there is none.

        Fail-soft like :meth:`get`: a corrupt file is logged and reads as
        empty. The result is the caller's own copy, so a caller that reads
        once can change it and hand it to :meth:`write`.
        """
        return self._read_mapping()

    def write(self, mapping: dict) -> None:
        """Replace the persisted state with *mapping*, in one write.

        A no-op when *storage* is ``None``.
        """
        if self._storage is None:
            return
        self._storage.write_json(_STATE_FILE_NAME, mapping)

    def set(self, key: str, value: str) -> None:
        """Durably persist *value* under *key*, leaving every other key untouched.

        A no-op when *storage* is ``None`` -- the device has nowhere durable
        to write, so the call is silently dropped rather than raising.
        """
        self.update({key: value})

    def clear(self, key: str) -> None:
        """Remove *key* from the persisted state, leaving every other key untouched.

        A no-op when *storage* is ``None``, or when *key* is already absent --
        clearing an unset key is an ordinary case, not an error.
        """
        self.update({}, remove=(key,))

    def update(self, values: dict[str, str], remove: tuple[str, ...] = ()) -> None:
        """Set every key in *values* and remove every key in *remove*, in one write.

        One read-modify-write, so the changes land together in one replace
        of the file (as atomic as :meth:`DeviceStorage.write_json` allows)
        rather than in separate writes a power loss could split. Absent keys
        in *remove* are skipped and every other key is left untouched; when
        nothing changes, nothing is written. A no-op when *storage* is
        ``None``.
        """
        if self._storage is None:
            return
        mapping = self._read_mapping()
        before = dict(mapping)
        for key in remove:
            mapping.pop(key, None)
        mapping.update(values)
        if mapping != before:
            self.write(mapping)

    def _read_mapping(self) -> dict:
        """Return the persisted state mapping, fail-soft on every bad case.

        A never-configured storage, a never-written file, malformed JSON,
        and valid-but-non-object JSON all fall through to an empty mapping
        rather than raising into the boot path; the latter two are logged
        so a corrupt card is visible without crashing the read.
        """
        if self._storage is None:
            return {}
        try:
            mapping = self._storage.read_json(_STATE_FILE_NAME)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            self._logger.log(f"{_STATE_FILE_NAME} is malformed JSON, treating as empty: {e}")
            return {}
        if mapping is None:
            return {}
        if not isinstance(mapping, dict):
            self._logger.log(f"{_STATE_FILE_NAME} content is not a JSON object, treating as empty")
            return {}
        return mapping

"""Behaviour-driven tests for DeviceSceneReboot (hardware/shared/device_reboot.py).

Each test injects a recording reset in place of ``microcontroller.reset``,
so a "reboot" only records what storage held (or how many writes it had seen)
at the moment it fired.
"""

from engine.log import Logger
from hardware.shared.device_reboot import DeviceSceneReboot
from hardware.shared.device_state import DeviceStateStore
from hardware.shared.device_storage import DeviceStorage


class RecordingReset:
    """A reset that records the persisted ``scene``/``return_to`` each time it is called."""

    def __init__(self, storage: DeviceStorage | None = None) -> None:
        self._storage = storage
        self.calls: list[tuple[str | None, str | None]] = []

    def __call__(self) -> None:
        store = DeviceStateStore(self._storage)
        self.calls.append((store.get("scene"), store.get("return_to")))


class WriteCountingStorage(DeviceStorage):
    """A real ``DeviceStorage`` that counts ``write_json`` calls, so a test can see writes land."""

    def __init__(self, mount_root: str) -> None:
        super().__init__(mount_root)
        self.json_writes = 0

    def write_json(self, name: str, mapping: dict) -> None:
        self.json_writes += 1
        super().write_json(name, mapping)


class WriteCountAtReset:
    """A reset that records how many ``write_json`` calls *storage* had seen when it fired."""

    def __init__(self, storage: WriteCountingStorage) -> None:
        self._storage = storage
        self.counts: list[int] = []

    def __call__(self) -> None:
        self.counts.append(self._storage.json_writes)


# ---------------------------------------------------------------------------
# reboot_into — persists scene + return_to, then resets
# ---------------------------------------------------------------------------


def test_reboot_into_persists_target_as_scene(device_storage):
    reboot = DeviceSceneReboot(device_storage, booted_scene="lobby", reset=RecordingReset())

    reboot.reboot_into("tag")

    assert DeviceStateStore(device_storage).get("scene") == "tag"


def test_reboot_into_records_the_booted_scene_as_return_to(device_storage):
    reboot = DeviceSceneReboot(device_storage, booted_scene="lobby", reset=RecordingReset())

    reboot.reboot_into("tag")

    assert DeviceStateStore(device_storage).get("return_to") == "lobby"


def test_reboot_into_resets_once_after_persisting(device_storage):
    reset = RecordingReset(device_storage)
    reboot = DeviceSceneReboot(device_storage, booted_scene="lobby", reset=reset)

    reboot.reboot_into("tag")

    assert reset.calls == [("tag", "lobby")]


def test_reboot_into_persists_in_one_write_before_resetting(tmp_path):
    storage = WriteCountingStorage(str(tmp_path))
    reset = WriteCountAtReset(storage)
    reboot = DeviceSceneReboot(storage, booted_scene="lobby", reset=reset)

    reboot.reboot_into("tag")

    assert reset.counts == [1]


def test_reboot_into_on_a_card_less_device_does_not_reset():
    reset = RecordingReset()
    reboot = DeviceSceneReboot(None, booted_scene="lobby", reset=reset)

    reboot.reboot_into("tag")

    assert reset.calls == []


def test_reboot_into_on_a_card_less_device_logs():
    lines: list[str] = []
    reboot = DeviceSceneReboot(
        None, booted_scene="lobby", reset=RecordingReset(), logger=Logger("[reboot]", lines.append)
    )

    reboot.reboot_into("tag")

    assert lines


# ---------------------------------------------------------------------------
# reboot_to_previous — persists return_to as scene, clears return_to, resets
# ---------------------------------------------------------------------------


def test_reboot_to_previous_persists_the_recorded_return_to_as_scene(device_storage):
    DeviceStateStore(device_storage).set("return_to", "lobby")
    reboot = DeviceSceneReboot(device_storage, booted_scene="tag", reset=RecordingReset())

    reboot.reboot_to_previous()

    assert DeviceStateStore(device_storage).get("scene") == "lobby"


def test_reboot_to_previous_clears_return_to(device_storage):
    DeviceStateStore(device_storage).set("return_to", "lobby")
    reboot = DeviceSceneReboot(device_storage, booted_scene="tag", reset=RecordingReset())

    reboot.reboot_to_previous()

    assert DeviceStateStore(device_storage).get("return_to") is None


def test_reboot_to_previous_resets_once_after_persisting(device_storage):
    DeviceStateStore(device_storage).set("return_to", "lobby")
    reset = RecordingReset(device_storage)
    reboot = DeviceSceneReboot(device_storage, booted_scene="tag", reset=reset)

    reboot.reboot_to_previous()

    assert reset.calls == [("lobby", None)]


def test_reboot_to_previous_persists_in_one_write_before_resetting(tmp_path):
    DeviceStateStore(DeviceStorage(str(tmp_path))).set("return_to", "lobby")
    storage = WriteCountingStorage(str(tmp_path))
    reset = WriteCountAtReset(storage)
    reboot = DeviceSceneReboot(storage, booted_scene="tag", reset=reset)

    reboot.reboot_to_previous()

    assert reset.counts == [1]


def test_reboot_to_previous_with_no_recorded_return_to_does_not_reset(device_storage):
    reset = RecordingReset()
    reboot = DeviceSceneReboot(device_storage, booted_scene="tag", reset=reset)

    reboot.reboot_to_previous()

    assert reset.calls == []


def test_reboot_to_previous_with_no_recorded_return_to_logs(device_storage):
    lines: list[str] = []
    reboot = DeviceSceneReboot(
        device_storage,
        booted_scene="tag",
        reset=RecordingReset(),
        logger=Logger("[reboot]", lines.append),
    )

    reboot.reboot_to_previous()

    assert lines


def test_reboot_to_previous_on_a_card_less_device_does_not_reset():
    reset = RecordingReset()
    reboot = DeviceSceneReboot(None, booted_scene="tag", reset=reset)

    reboot.reboot_to_previous()

    assert reset.calls == []


def test_reboot_to_previous_on_a_card_less_device_logs():
    lines: list[str] = []
    reboot = DeviceSceneReboot(
        None, booted_scene="tag", reset=RecordingReset(), logger=Logger("[reboot]", lines.append)
    )

    reboot.reboot_to_previous()

    assert lines


# ---------------------------------------------------------------------------
# previous_scene — the scene reboot_to_previous would boot
# ---------------------------------------------------------------------------


def test_previous_scene_is_the_recorded_return_to(device_storage):
    DeviceStateStore(device_storage).set("return_to", "lobby")
    reboot = DeviceSceneReboot(device_storage, booted_scene="tag", reset=RecordingReset())

    assert reboot.previous_scene() == "lobby"


def test_previous_scene_is_none_when_no_return_to_is_recorded(device_storage):
    reboot = DeviceSceneReboot(device_storage, booted_scene="tag", reset=RecordingReset())

    assert reboot.previous_scene() is None


def test_previous_scene_is_none_on_a_card_less_device():
    reboot = DeviceSceneReboot(None, booted_scene="tag", reset=RecordingReset())

    assert reboot.previous_scene() is None

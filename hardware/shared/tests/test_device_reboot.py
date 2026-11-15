"""Behaviour-driven tests for DeviceSceneReboot (hardware/shared/device_reboot.py).

Each test injects a recording reset in place of ``microcontroller.reset``,
so a "reboot" only records what the Persisted scene record held at the
moment it fired. The record's own rules, one write per change among them,
are pinned in ``test_persisted_scene.py``.
"""

from engine.log import Logger
from hardware.shared.device_reboot import DeviceSceneReboot
from hardware.shared.device_state import DeviceStateStore
from hardware.shared.persisted_scene import PersistedScene

_DEFAULT = {"default_scene": "hardware_test"}


class RecordingReset:
    """A reset that records ``(persisted, previous)`` from *record* each time it is called."""

    def __init__(self, record: PersistedScene | None = None) -> None:
        self._record = record
        self.calls: list[tuple[str | None, str | None]] = []

    def __call__(self) -> None:
        assert self._record is not None
        persisted, _ = self._record.boot_candidates(_DEFAULT)
        self.calls.append((persisted, self._record.previous_scene()))


def _record(device_storage) -> PersistedScene:
    return PersistedScene(DeviceStateStore(device_storage))


# ---------------------------------------------------------------------------
# reboot_into — records the target and the scene being left, then resets
# ---------------------------------------------------------------------------


def test_reboot_into_records_the_target_and_the_booted_scene_then_resets(device_storage):
    record = _record(device_storage)
    reset = RecordingReset(record)
    reboot = DeviceSceneReboot(record, booted_scene="lobby", reset=reset)

    reboot.reboot_into("tag")

    assert reset.calls == [("tag", "lobby")]


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
# reboot_to_previous — records the return, then resets
# ---------------------------------------------------------------------------


def test_reboot_to_previous_records_the_return_then_resets(device_storage):
    record = _record(device_storage)
    record.record_reboot("tag", "lobby")
    reset = RecordingReset(record)
    reboot = DeviceSceneReboot(record, booted_scene="tag", reset=reset)

    reboot.reboot_to_previous()

    assert reset.calls == [("lobby", None)]


def test_reboot_to_previous_with_no_recorded_return_to_does_not_reset(device_storage):
    record = _record(device_storage)
    reset = RecordingReset(record)
    reboot = DeviceSceneReboot(record, booted_scene="tag", reset=reset)

    reboot.reboot_to_previous()

    assert reset.calls == []


def test_reboot_to_previous_with_no_recorded_return_to_logs(device_storage):
    lines: list[str] = []
    reboot = DeviceSceneReboot(
        _record(device_storage),
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
    record = _record(device_storage)
    record.record_reboot("tag", "lobby")
    reboot = DeviceSceneReboot(record, booted_scene="tag", reset=RecordingReset())

    assert reboot.previous_scene() == "lobby"


def test_previous_scene_is_none_when_no_return_to_is_recorded(device_storage):
    reboot = DeviceSceneReboot(_record(device_storage), booted_scene="tag", reset=RecordingReset())

    assert reboot.previous_scene() is None


def test_previous_scene_is_none_on_a_card_less_device():
    reboot = DeviceSceneReboot(None, booted_scene="tag", reset=RecordingReset())

    assert reboot.previous_scene() is None

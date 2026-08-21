"""Behaviour-driven tests for DeviceSceneReboot (hardware/circuitpython/device_reboot.py).

``microcontroller`` is stubbed into ``sys.modules`` by the sibling
conftest.py so this suite runs under CPython; ``reset`` itself is patched
per test via ``patch`` so a "reboot" never actually happens.
"""

from unittest.mock import patch

from engine.log import Logger
from hardware.circuitpython.device_reboot import DeviceSceneReboot
from hardware.shared.device_state import DeviceStateStore
from hardware.shared.tests.helpers import FakeDeviceStorage

# ---------------------------------------------------------------------------
# reboot_into — persists scene + return_to, then resets
# ---------------------------------------------------------------------------


def test_reboot_into_persists_target_as_scene():
    storage = FakeDeviceStorage()
    reboot = DeviceSceneReboot(storage, booted_scene="lobby")

    with patch("hardware.circuitpython.device_reboot.microcontroller.reset"):
        reboot.reboot_into("tag")

    assert DeviceStateStore(storage).get("scene") == "tag"


def test_reboot_into_records_the_booted_scene_as_return_to():
    storage = FakeDeviceStorage()
    reboot = DeviceSceneReboot(storage, booted_scene="lobby")

    with patch("hardware.circuitpython.device_reboot.microcontroller.reset"):
        reboot.reboot_into("tag")

    assert DeviceStateStore(storage).get("return_to") == "lobby"


def test_reboot_into_resets_the_device():
    storage = FakeDeviceStorage()
    reboot = DeviceSceneReboot(storage, booted_scene="lobby")

    with patch("hardware.circuitpython.device_reboot.microcontroller.reset") as mock_reset:
        reboot.reboot_into("tag")

    mock_reset.assert_called_once_with()


def test_reboot_into_on_a_card_less_device_does_not_reset():
    reboot = DeviceSceneReboot(None, booted_scene="lobby")

    with patch("hardware.circuitpython.device_reboot.microcontroller.reset") as mock_reset:
        reboot.reboot_into("tag")

    mock_reset.assert_not_called()


def test_reboot_into_on_a_card_less_device_logs():
    lines = []
    reboot = DeviceSceneReboot(None, booted_scene="lobby", logger=Logger("[reboot]", lines.append))

    with patch("hardware.circuitpython.device_reboot.microcontroller.reset"):
        reboot.reboot_into("tag")

    assert lines


# ---------------------------------------------------------------------------
# reboot_to_previous — persists return_to as scene, clears return_to, resets
# ---------------------------------------------------------------------------


def test_reboot_to_previous_persists_the_recorded_return_to_as_scene():
    storage = FakeDeviceStorage()
    DeviceStateStore(storage).set("return_to", "lobby")
    reboot = DeviceSceneReboot(storage, booted_scene="tag")

    with patch("hardware.circuitpython.device_reboot.microcontroller.reset"):
        reboot.reboot_to_previous()

    assert DeviceStateStore(storage).get("scene") == "lobby"


def test_reboot_to_previous_clears_return_to():
    storage = FakeDeviceStorage()
    DeviceStateStore(storage).set("return_to", "lobby")
    reboot = DeviceSceneReboot(storage, booted_scene="tag")

    with patch("hardware.circuitpython.device_reboot.microcontroller.reset"):
        reboot.reboot_to_previous()

    assert DeviceStateStore(storage).get("return_to") is None


def test_reboot_to_previous_resets_the_device():
    storage = FakeDeviceStorage()
    DeviceStateStore(storage).set("return_to", "lobby")
    reboot = DeviceSceneReboot(storage, booted_scene="tag")

    with patch("hardware.circuitpython.device_reboot.microcontroller.reset") as mock_reset:
        reboot.reboot_to_previous()

    mock_reset.assert_called_once_with()


def test_reboot_to_previous_with_no_recorded_return_to_does_not_reset():
    storage = FakeDeviceStorage()
    reboot = DeviceSceneReboot(storage, booted_scene="tag")

    with patch("hardware.circuitpython.device_reboot.microcontroller.reset") as mock_reset:
        reboot.reboot_to_previous()

    mock_reset.assert_not_called()


def test_reboot_to_previous_with_no_recorded_return_to_logs():
    storage = FakeDeviceStorage()
    lines = []
    reboot = DeviceSceneReboot(storage, booted_scene="tag", logger=Logger("[reboot]", lines.append))

    with patch("hardware.circuitpython.device_reboot.microcontroller.reset"):
        reboot.reboot_to_previous()

    assert lines


def test_reboot_to_previous_on_a_card_less_device_does_not_reset():
    reboot = DeviceSceneReboot(None, booted_scene="tag")

    with patch("hardware.circuitpython.device_reboot.microcontroller.reset") as mock_reset:
        reboot.reboot_to_previous()

    mock_reset.assert_not_called()


def test_reboot_to_previous_on_a_card_less_device_logs():
    lines = []
    reboot = DeviceSceneReboot(None, booted_scene="tag", logger=Logger("[reboot]", lines.append))

    with patch("hardware.circuitpython.device_reboot.microcontroller.reset"):
        reboot.reboot_to_previous()

    assert lines

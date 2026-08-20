"""Behaviour-driven tests for DeviceStateStore, the aura-state.json owner.

Exercises DeviceStateStore (hardware/shared/device_state.py) against the shared
FakeDeviceStorage double (hardware/shared/tests/helpers.py), the same seam
DeviceStorage's own tests use.
"""

from engine.log import Logger
from hardware.shared.device_state import DeviceStateStore
from hardware.shared.tests.helpers import FakeDeviceStorage


def test_get_returns_none_for_a_never_written_key():
    store = DeviceStateStore(FakeDeviceStorage())

    assert store.get("scene") is None


def test_set_then_get_round_trips_a_value():
    store = DeviceStateStore(FakeDeviceStorage())

    store.set("scene", "tag")

    assert store.get("scene") == "tag"


def test_a_fresh_store_over_the_same_storage_reads_back_a_prior_write():
    storage = FakeDeviceStorage()
    DeviceStateStore(storage).set("scene", "red_light_green_light")

    rebooted_store = DeviceStateStore(storage)

    assert rebooted_store.get("scene") == "red_light_green_light"


def test_a_fresh_store_over_the_same_storage_reads_back_both_scene_and_return_to():
    storage = FakeDeviceStorage()
    writer = DeviceStateStore(storage)
    writer.set("scene", "tag")
    writer.set("return_to", "lobby")

    rebooted_store = DeviceStateStore(storage)

    assert rebooted_store.get("scene") == "tag"
    assert rebooted_store.get("return_to") == "lobby"


def test_setting_one_key_preserves_a_previously_set_other_key():
    store = DeviceStateStore(FakeDeviceStorage())
    store.set("scene", "tag")
    store.set("return_to", "lobby")

    store.set("scene", "hardware_test")

    assert store.get("scene") == "hardware_test"
    assert store.get("return_to") == "lobby"


def test_malformed_json_reads_as_a_never_written_key_rather_than_raising():
    storage = FakeDeviceStorage()
    storage.write_bytes("aura-state.json", b"{not valid json")
    store = DeviceStateStore(storage)

    assert store.get("scene") is None


def test_non_object_json_reads_as_a_never_written_key_rather_than_raising():
    storage = FakeDeviceStorage()
    storage.write_json("aura-state.json", ["scene", "tag"])
    store = DeviceStateStore(storage)

    assert store.get("scene") is None


def test_malformed_json_logs_the_fail_soft_read():
    storage = FakeDeviceStorage()
    storage.write_bytes("aura-state.json", b"{not valid json")
    lines = []
    store = DeviceStateStore(storage, logger=Logger("[state]", sink=lines.append))

    store.get("scene")

    assert lines


def test_a_well_formed_read_logs_nothing():
    storage = FakeDeviceStorage()
    storage.write_json("aura-state.json", {"scene": "tag"})
    lines = []
    store = DeviceStateStore(storage, logger=Logger("[state]", sink=lines.append))

    store.get("scene")

    assert lines == []


def test_no_storage_reads_as_empty_state():
    store = DeviceStateStore(None)

    assert store.get("scene") is None


def test_no_storage_makes_a_write_a_silent_no_op():
    store = DeviceStateStore(None)

    store.set("scene", "tag")

    assert store.get("scene") is None

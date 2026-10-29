"""Behaviour-driven tests for DeviceStateStore, the aura-state.json owner.

Exercises DeviceStateStore (hardware/shared/device_state.py) against a real
DeviceStorage over a temporary card directory (the shared ``device_storage``
fixture), so it exercises the storage devices run.
"""

from engine.log import Logger
from hardware.shared.device_state import DeviceStateStore


def test_get_returns_none_for_a_never_written_key(device_storage):
    store = DeviceStateStore(device_storage)

    assert store.get("scene") is None


def test_set_then_get_round_trips_a_value(device_storage):
    store = DeviceStateStore(device_storage)

    store.set("scene", "tag")

    assert store.get("scene") == "tag"


def test_a_fresh_store_over_the_same_storage_reads_back_a_prior_write(device_storage):
    DeviceStateStore(device_storage).set("scene", "red_light_green_light")

    rebooted_store = DeviceStateStore(device_storage)

    assert rebooted_store.get("scene") == "red_light_green_light"


def test_a_fresh_store_over_the_same_storage_reads_back_both_scene_and_return_to(device_storage):
    writer = DeviceStateStore(device_storage)
    writer.set("scene", "tag")
    writer.set("return_to", "lobby")

    rebooted_store = DeviceStateStore(device_storage)

    assert rebooted_store.get("scene") == "tag"
    assert rebooted_store.get("return_to") == "lobby"


def test_setting_one_key_preserves_a_previously_set_other_key(device_storage):
    store = DeviceStateStore(device_storage)
    store.set("scene", "tag")
    store.set("return_to", "lobby")

    store.set("scene", "hardware_test")

    assert store.get("scene") == "hardware_test"
    assert store.get("return_to") == "lobby"


def test_malformed_json_reads_as_a_never_written_key_rather_than_raising(device_storage):
    device_storage.write_bytes("aura-state.json", b"{not valid json")
    store = DeviceStateStore(device_storage)

    assert store.get("scene") is None


def test_non_object_json_reads_as_a_never_written_key_rather_than_raising(device_storage):
    device_storage.write_json("aura-state.json", ["scene", "tag"])
    store = DeviceStateStore(device_storage)

    assert store.get("scene") is None


def test_non_utf8_content_reads_as_a_never_written_key_rather_than_raising(device_storage):
    device_storage.write_bytes("aura-state.json", b"\xff\xfe not valid utf-8")
    store = DeviceStateStore(device_storage)

    assert store.get("scene") is None


def test_a_missing_key_within_an_otherwise_valid_object_reads_as_absent(device_storage):
    device_storage.write_json("aura-state.json", {"scene": "tag"})
    store = DeviceStateStore(device_storage)

    assert store.get("return_to") is None


def test_malformed_json_logs_the_fail_soft_read(device_storage):
    device_storage.write_bytes("aura-state.json", b"{not valid json")
    lines = []
    store = DeviceStateStore(device_storage, logger=Logger("[state]", sink=lines.append))

    store.get("scene")

    assert lines


def test_non_object_json_logs_the_fail_soft_read(device_storage):
    device_storage.write_json("aura-state.json", ["scene", "tag"])
    lines = []
    store = DeviceStateStore(device_storage, logger=Logger("[state]", sink=lines.append))

    store.get("scene")

    assert lines


def test_a_well_formed_read_logs_nothing(device_storage):
    device_storage.write_json("aura-state.json", {"scene": "tag"})
    lines = []
    store = DeviceStateStore(device_storage, logger=Logger("[state]", sink=lines.append))

    store.get("scene")

    assert lines == []


def test_no_storage_reads_as_empty_state():
    store = DeviceStateStore(None)

    assert store.get("scene") is None


def test_no_storage_makes_a_write_a_silent_no_op():
    store = DeviceStateStore(None)

    store.set("scene", "tag")

    assert store.get("scene") is None


def test_clear_removes_a_previously_set_key(device_storage):
    store = DeviceStateStore(device_storage)
    store.set("return_to", "lobby")

    store.clear("return_to")

    assert store.get("return_to") is None


def test_clear_preserves_a_different_key(device_storage):
    store = DeviceStateStore(device_storage)
    store.set("scene", "tag")
    store.set("return_to", "lobby")

    store.clear("return_to")

    assert store.get("scene") == "tag"


def test_clear_of_an_already_absent_key_is_a_no_op(device_storage):
    store = DeviceStateStore(device_storage)
    store.set("scene", "tag")

    store.clear("return_to")

    assert store.get("scene") == "tag"


def test_no_storage_makes_clear_a_silent_no_op():
    store = DeviceStateStore(None)

    store.clear("return_to")  # must not raise


def test_update_sets_and_removes_keys_in_one_call_preserving_every_other_key(device_storage):
    store = DeviceStateStore(device_storage)
    store.set("scene", "tag")
    store.set("return_to", "lobby")
    store.set("brightness", "high")

    store.update({"scene_deploy_token": "a1b2"}, remove=("scene", "return_to"))

    rebooted_store = DeviceStateStore(device_storage)
    assert rebooted_store.get("scene_deploy_token") == "a1b2"
    assert rebooted_store.get("scene") is None
    assert rebooted_store.get("return_to") is None
    assert rebooted_store.get("brightness") == "high"


def test_update_removing_an_absent_key_still_sets_the_others(device_storage):
    store = DeviceStateStore(device_storage)

    store.update({"scene_deploy_token": "a1b2"}, remove=("scene",))

    assert store.get("scene_deploy_token") == "a1b2"


def test_update_over_malformed_json_writes_a_fresh_object(device_storage):
    device_storage.write_bytes("aura-state.json", b"{not valid json")
    store = DeviceStateStore(device_storage)

    store.update({"scene_deploy_token": "a1b2"}, remove=("scene",))

    assert store.get("scene_deploy_token") == "a1b2"


def test_no_storage_makes_update_a_silent_no_op():
    store = DeviceStateStore(None)

    store.update({"scene_deploy_token": "a1b2"}, remove=("scene",))

    assert store.get("scene_deploy_token") is None


def test_write_replaces_the_whole_persisted_state(device_storage):
    store = DeviceStateStore(device_storage)
    store.set("scene", "tag")

    store.write({"return_to": "lobby"})

    rebooted_store = DeviceStateStore(device_storage)
    assert rebooted_store.read() == {"return_to": "lobby"}

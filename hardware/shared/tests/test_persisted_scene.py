"""Behaviour-driven tests for PersistedScene, the Persisted scene record on the card.

Each test runs ``PersistedScene`` over a real ``DeviceStateStore`` and
``DeviceStorage`` card directory (the shared ``device_storage`` fixture), and
reads the record back through ``PersistedScene`` itself. Only
``test_the_record_on_the_card_has_a_fixed_json_layout`` reads the raw file.
"""

import json

import pytest

from engine.log import Logger
from hardware.shared.device_state import DeviceStateStore
from hardware.shared.device_storage import DeviceStorage
from hardware.shared.persisted_scene import PersistedScene
from hardware.shared.scene_selection import with_scene_deploy
from hardware.shared.tests.write_counting_storage import WriteCountingStorage

_DEFAULT = {"default_scene": "red_light_green_light"}
"""A boot mapping with a flash ``default_scene`` and no Scene deploy token."""


def _persisted_scene(storage: DeviceStorage | None, logger: Logger | None = None) -> PersistedScene:
    return PersistedScene(DeviceStateStore(storage, logger), logger)


@pytest.fixture
def counting_storage(device_storage) -> WriteCountingStorage:
    """A write-counting storage over the ``device_storage`` card directory."""
    return WriteCountingStorage(device_storage.mount_root)


def test_a_persisted_scene_is_tried_before_a_different_flash_default(device_storage):
    record = _persisted_scene(device_storage)
    record.record_reboot("tag", "lobby")

    assert record.boot_candidates(_DEFAULT) == ("tag", "red_light_green_light")


def test_a_persisted_scene_without_a_flash_default_is_the_fallback(device_storage):
    record = _persisted_scene(device_storage)
    record.record_reboot("tag", "lobby")

    assert record.boot_candidates({}) == (None, "tag")


def test_a_persisted_scene_equal_to_the_flash_default_is_only_the_fallback(device_storage):
    record = _persisted_scene(device_storage)
    record.record_reboot("tag", "lobby")

    assert record.boot_candidates({"default_scene": "tag"}) == (None, "tag")


def test_no_persisted_scene_falls_back_to_the_flash_default(device_storage):
    assert _persisted_scene(device_storage).boot_candidates(_DEFAULT) == (
        None,
        "red_light_green_light",
    )


def test_neither_a_persisted_nor_a_flash_scene_raises_naming_both_files(device_storage):
    with pytest.raises(ValueError, match=r"aura-state\.json.*aura-boot\.json"):
        _persisted_scene(device_storage).boot_candidates({})


def test_a_non_string_flash_default_is_treated_as_absent_and_raises(device_storage):
    with pytest.raises(
        ValueError, match=r"no boot scene: neither a Persisted scene \(aura-state\.json"
    ):
        _persisted_scene(device_storage).boot_candidates({"default_scene": 42})


def test_a_card_less_device_falls_back_to_the_flash_default():
    assert _persisted_scene(None).boot_candidates(_DEFAULT) == (None, "red_light_green_light")


def test_an_older_cards_unprefixed_scene_key_is_ignored(device_storage):
    device_storage.write_json("aura-state.json", {"scene": "tag", "return_to": "lobby"})
    record = _persisted_scene(device_storage)

    assert record.boot_candidates(_DEFAULT) == (None, "red_light_green_light")
    assert record.previous_scene() is None


def test_recording_a_reboot_records_the_scene_being_left_as_the_previous_scene(device_storage):
    record = _persisted_scene(device_storage)

    record.record_reboot("tag", "lobby")

    assert record.previous_scene() == "lobby"


def test_previous_scene_is_none_when_nothing_was_recorded(device_storage):
    assert _persisted_scene(device_storage).previous_scene() is None


def test_previous_scene_is_none_on_a_card_less_device():
    assert _persisted_scene(None).previous_scene() is None


def test_recording_a_return_makes_the_previous_scene_the_persisted_scene(device_storage):
    record = _persisted_scene(device_storage)
    record.record_reboot("tag", "lobby")

    target = record.record_return()

    assert target == "lobby"
    assert record.boot_candidates(_DEFAULT) == ("lobby", "red_light_green_light")


def test_recording_a_return_clears_the_previous_scene(device_storage):
    record = _persisted_scene(device_storage)
    record.record_reboot("tag", "lobby")

    record.record_return()

    assert record.previous_scene() is None


def test_recording_a_return_with_nothing_recorded_returns_none_and_writes_nothing(
    counting_storage,
):
    record = _persisted_scene(counting_storage)

    assert record.record_return() is None
    assert counting_storage.json_writes == 0


@pytest.mark.parametrize(
    "change",
    [
        lambda record: record.record_reboot("tag", "lobby"),
        lambda record: record.record_return(),
        lambda record: record.apply_scene_deploy(with_scene_deploy(_DEFAULT, "tag", "c3d4")),
    ],
    ids=["record_reboot", "record_return", "apply_scene_deploy"],
)
def test_each_change_to_the_record_is_one_write(device_storage, counting_storage, change):
    _persisted_scene(device_storage).record_reboot("hardware_test", "lobby")
    record = _persisted_scene(counting_storage)

    change(record)

    assert counting_storage.json_writes == 1


@pytest.mark.parametrize(
    "change",
    [
        lambda record: record.record_reboot("tag", "lobby"),
        lambda record: record.record_return(),
        lambda record: record.apply_scene_deploy(with_scene_deploy(_DEFAULT, "tag", "c3d4")),
    ],
    ids=["record_reboot", "record_return", "apply_scene_deploy"],
)
def test_every_change_to_the_record_keeps_other_keys_in_the_state_file(device_storage, change):
    store = DeviceStateStore(device_storage)
    record = PersistedScene(store)
    record.record_reboot("hardware_test", "lobby")
    store.set("reboot_demo_phase", "into")

    change(record)

    assert store.get("reboot_demo_phase") == "into"


def test_a_new_scene_deploy_token_clears_the_persisted_scene(device_storage):
    record = _persisted_scene(device_storage)
    record.record_reboot("tag", "lobby")
    boot_values = with_scene_deploy({}, "red_light_green_light", "c3d4")

    record.apply_scene_deploy(boot_values)

    assert record.boot_candidates(boot_values) == (None, "red_light_green_light")


def test_a_new_scene_deploy_token_clears_the_previous_scene(device_storage):
    record = _persisted_scene(device_storage)
    record.record_reboot("tag", "lobby")

    record.apply_scene_deploy(with_scene_deploy({}, "red_light_green_light", "c3d4"))

    assert record.previous_scene() is None


def test_an_applied_scene_deploy_token_no_longer_clears_the_persisted_scene(device_storage):
    record = _persisted_scene(device_storage)
    boot_values = with_scene_deploy({}, "red_light_green_light", "c3d4")
    record.apply_scene_deploy(boot_values)
    record.record_reboot("tag", "lobby")

    record.apply_scene_deploy(boot_values)

    assert record.boot_candidates(boot_values) == ("tag", "red_light_green_light")


def test_applying_a_new_scene_deploy_token_logs_the_deployed_and_cleared_scenes(device_storage):
    lines: list[str] = []
    record = _persisted_scene(device_storage, Logger("[boot]", sink=lines.append))
    record.record_reboot("tag", "lobby")

    record.apply_scene_deploy(with_scene_deploy({}, "red_light_green_light", "c3d4"))

    assert lines == [
        "[boot] scene deploy c3d4 applied: booting 'red_light_green_light', cleared 'tag'\n"
    ]


@pytest.mark.parametrize("token", ["", 42, None])
def test_an_empty_or_non_string_scene_deploy_token_keeps_the_persisted_scene_and_logs_nothing(
    device_storage, token
):
    lines: list[str] = []
    record = _persisted_scene(device_storage, Logger("[boot]", sink=lines.append))
    record.record_reboot("tag", "lobby")
    boot_values = {**_DEFAULT, "scene_deploy_token": token}

    record.apply_scene_deploy(boot_values)

    assert record.boot_candidates(boot_values)[0] == "tag"
    assert lines == []


def test_applying_a_scene_deploy_on_a_card_less_device_logs_nothing():
    lines: list[str] = []
    record = _persisted_scene(None, Logger("[boot]", sink=lines.append))

    record.apply_scene_deploy(with_scene_deploy({}, "tag", "c3d4"))

    assert lines == []


def test_applying_a_scene_deploy_over_a_malformed_card_logs_the_malformed_card_once(device_storage):
    device_storage.write_bytes("aura-state.json", b"{not valid json")
    lines: list[str] = []

    _persisted_scene(device_storage, Logger("[boot]", sink=lines.append)).apply_scene_deploy(
        with_scene_deploy({}, "tag", "a1b2")
    )

    assert len([line for line in lines if "malformed" in line]) == 1


def test_the_record_on_the_card_has_a_fixed_json_layout(device_storage):
    record = _persisted_scene(device_storage)
    record.apply_scene_deploy(with_scene_deploy({}, "lobby", "c3d4"))

    record.record_reboot("tag", "lobby")

    assert json.loads(_read(device_storage)) == {
        "persisted_scene.scene": "tag",
        "persisted_scene.return_to": "lobby",
        "persisted_scene.deploy_token": "c3d4",
    }


def _read(storage: DeviceStorage) -> str:
    with open(storage.path("aura-state.json"), encoding="utf-8") as state_file:
        return state_file.read()

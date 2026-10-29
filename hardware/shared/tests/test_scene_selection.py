"""Behaviour-driven tests for the pure scene-name resolver."""

import pytest

from engine.log import Logger
from hardware.shared.scene_selection import (
    apply_scene_deploy,
    resolve_boot_scene,
    resolve_scene_name,
)


def test_present_scene_name_is_used():
    assert resolve_scene_name({"default_scene": "red_light_green_light"}) == "red_light_green_light"


def test_absent_scene_raises():
    with pytest.raises(ValueError, match=r"default_scene"):
        resolve_scene_name({})


def test_empty_scene_raises():
    with pytest.raises(ValueError, match=r"default_scene"):
        resolve_scene_name({"default_scene": ""})


def test_non_string_scene_raises():
    with pytest.raises(ValueError, match=r"default_scene"):
        resolve_scene_name({"default_scene": 42})


def test_persisted_sd_scene_wins_over_flash_default(device_storage):
    device_storage.write_json("aura-state.json", {"scene": "tag"})

    scene = resolve_boot_scene(device_storage, {"default_scene": "red_light_green_light"})

    assert scene == "tag"


def test_persisted_sd_scene_used_when_flash_default_is_absent(device_storage):
    device_storage.write_json("aura-state.json", {"scene": "tag"})

    scene = resolve_boot_scene(device_storage, {})

    assert scene == "tag"


def test_no_persisted_scene_falls_back_to_flash_default(device_storage):
    scene = resolve_boot_scene(device_storage, {"default_scene": "red_light_green_light"})

    assert scene == "red_light_green_light"


def test_neither_persisted_nor_flash_scene_raises_naming_both_files(device_storage):
    with pytest.raises(ValueError, match=r"aura-state\.json.*aura-settings\.json"):
        resolve_boot_scene(device_storage, {})


def test_empty_persisted_scene_falls_back_to_flash_default(device_storage):
    device_storage.write_json("aura-state.json", {"scene": ""})

    scene = resolve_boot_scene(device_storage, {"default_scene": "red_light_green_light"})

    assert scene == "red_light_green_light"


def test_non_string_persisted_scene_falls_back_to_flash_default(device_storage):
    device_storage.write_json("aura-state.json", {"scene": 42})

    scene = resolve_boot_scene(device_storage, {"default_scene": "red_light_green_light"})

    assert scene == "red_light_green_light"


def test_non_string_flash_default_is_treated_as_absent_and_raises(device_storage):
    with pytest.raises(ValueError):
        resolve_boot_scene(device_storage, {"default_scene": 42})


def test_card_less_device_falls_back_to_flash_default():
    scene = resolve_boot_scene(None, {"default_scene": "red_light_green_light"})

    assert scene == "red_light_green_light"


def test_applying_a_scene_deploy_over_a_malformed_card_logs_the_malformed_card_once(device_storage):
    device_storage.write_bytes("aura-state.json", b"{not valid json")
    lines = []

    apply_scene_deploy(
        device_storage,
        {"default_scene": "tag", "scene_deploy_token": "a1b2"},
        Logger("[boot]", sink=lines.append),
    )

    assert len([line for line in lines if "malformed" in line]) == 1


@pytest.mark.parametrize("token", ["", 42, None])
def test_an_empty_or_non_string_scene_deploy_token_keeps_the_persisted_scene_and_logs_nothing(
    device_storage, token
):
    device_storage.write_json("aura-state.json", {"scene": "tag"})
    settings = {"default_scene": "red_light_green_light", "scene_deploy_token": token}
    lines = []

    apply_scene_deploy(device_storage, settings, Logger("[boot]", sink=lines.append))

    assert resolve_boot_scene(device_storage, settings) == "tag"
    assert lines == []

"""Behaviour-driven tests for the pure scene-name resolver."""

import pytest

from hardware.shared.scene_selection import resolve_boot_scene, resolve_scene_name
from hardware.shared.tests.helpers import FakeDeviceStorage


def test_present_scene_name_is_used():
    assert resolve_scene_name({"default_scene": "red_light_green_light"}) == "red_light_green_light"


def test_absent_scene_raises():
    with pytest.raises(ValueError):
        resolve_scene_name({})


def test_empty_scene_raises():
    with pytest.raises(ValueError):
        resolve_scene_name({"default_scene": ""})


def test_non_string_scene_raises():
    with pytest.raises(ValueError):
        resolve_scene_name({"default_scene": 42})


def test_persisted_sd_scene_wins_over_flash_default():
    storage = FakeDeviceStorage()
    storage.write_json("aura-state.json", {"scene": "tag"})

    scene = resolve_boot_scene(storage, {"default_scene": "red_light_green_light"})

    assert scene == "tag"


def test_persisted_sd_scene_used_when_flash_default_is_absent():
    storage = FakeDeviceStorage()
    storage.write_json("aura-state.json", {"scene": "tag"})

    scene = resolve_boot_scene(storage, {})

    assert scene == "tag"


def test_no_persisted_scene_falls_back_to_flash_default():
    storage = FakeDeviceStorage()

    scene = resolve_boot_scene(storage, {"default_scene": "red_light_green_light"})

    assert scene == "red_light_green_light"


def test_neither_persisted_nor_flash_scene_raises_naming_both_files():
    storage = FakeDeviceStorage()

    with pytest.raises(ValueError, match=r"aura-state\.json.*aura-settings\.json"):
        resolve_boot_scene(storage, {})


def test_empty_persisted_scene_falls_back_to_flash_default():
    storage = FakeDeviceStorage()
    storage.write_json("aura-state.json", {"scene": ""})

    scene = resolve_boot_scene(storage, {"default_scene": "red_light_green_light"})

    assert scene == "red_light_green_light"


def test_non_string_persisted_scene_falls_back_to_flash_default():
    storage = FakeDeviceStorage()
    storage.write_json("aura-state.json", {"scene": 42})

    scene = resolve_boot_scene(storage, {"default_scene": "red_light_green_light"})

    assert scene == "red_light_green_light"


def test_non_string_flash_default_is_treated_as_absent_and_raises():
    storage = FakeDeviceStorage()

    with pytest.raises(ValueError):
        resolve_boot_scene(storage, {"default_scene": 42})


def test_card_less_device_falls_back_to_flash_default():
    scene = resolve_boot_scene(None, {"default_scene": "red_light_green_light"})

    assert scene == "red_light_green_light"

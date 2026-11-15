"""Behaviour-driven tests for the flash side of scene selection: default_scene and Scene deploys."""

import pytest

from hardware.shared.scene_selection import (
    SCENE_DEPLOY_TOKEN_KEY,
    resolve_scene_name,
    with_scene_deploy,
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


def test_a_scene_deploy_write_sets_the_scene_and_token_and_keeps_other_boot_values():
    boot_values = {"default_scene": "tag", "brightness": 0.4}

    written = with_scene_deploy(boot_values, "red_light_green_light", "c3d4")

    assert written == {
        "default_scene": "red_light_green_light",
        SCENE_DEPLOY_TOKEN_KEY: "c3d4",
        "brightness": 0.4,
    }


def test_a_scene_deploy_write_leaves_the_given_boot_values_unchanged():
    boot_values = {"default_scene": "tag"}

    with_scene_deploy(boot_values, "red_light_green_light", "c3d4")

    assert boot_values == {"default_scene": "tag"}

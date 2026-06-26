"""Behaviour-driven tests for the pure scene-name resolver."""

from hardware.shared.scene_selection import DEFAULT_SCENE, resolve_scene_name


def test_present_scene_name_is_used():
    assert resolve_scene_name({"scene": "red_light_green_light"}) == "red_light_green_light"


def test_absent_scene_falls_back_to_default():
    assert resolve_scene_name({}) == DEFAULT_SCENE


def test_empty_scene_falls_back_to_default():
    assert resolve_scene_name({"scene": ""}) == DEFAULT_SCENE


def test_non_string_scene_falls_back_to_default():
    assert resolve_scene_name({"scene": 42}) == DEFAULT_SCENE


def test_default_scene_is_hardware_test():
    assert DEFAULT_SCENE == "hardware_test"

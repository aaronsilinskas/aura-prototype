"""Behaviour-driven tests for the pure scene-name resolver."""

import pytest

from hardware.shared.scene_selection import resolve_scene_name


def test_present_scene_name_is_used():
    assert resolve_scene_name({"scene": "red_light_green_light"}) == "red_light_green_light"


def test_absent_scene_raises():
    with pytest.raises(ValueError):
        resolve_scene_name({})


def test_empty_scene_raises():
    with pytest.raises(ValueError):
        resolve_scene_name({"scene": ""})


def test_non_string_scene_raises():
    with pytest.raises(ValueError):
        resolve_scene_name({"scene": 42})

"""Behaviour-driven tests for hardware/shared/device_settings.py."""

import json

import pytest

from hardware.shared.device_settings import read_settings_mapping


def test_read_settings_mapping_preserves_keys_from_the_file(tmp_path):
    path = tmp_path / "aura-settings.json"
    path.write_text(json.dumps({"default_scene": "tag"}))

    result = read_settings_mapping(str(path))

    assert result == {"default_scene": "tag"}


def test_read_settings_mapping_raises_when_file_absent(tmp_path):
    with pytest.raises(RuntimeError, match="not found"):
        read_settings_mapping(str(tmp_path / "missing.json"))


def test_read_settings_mapping_raises_when_file_is_malformed(tmp_path):
    path = tmp_path / "aura-settings.json"
    path.write_text("{not valid json")

    with pytest.raises(json.JSONDecodeError):
        read_settings_mapping(str(path))

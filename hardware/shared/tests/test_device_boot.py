"""Behaviour-driven tests for hardware/shared/device_boot.py."""

import json

import pytest

from hardware.shared.device_boot import read_boot_mapping


def test_read_boot_mapping_preserves_keys_from_the_file(tmp_path):
    path = tmp_path / "aura-boot.json"
    path.write_text(json.dumps({"default_scene": "tag"}))

    result = read_boot_mapping(str(path))

    assert result == {"default_scene": "tag"}


def test_read_boot_mapping_raises_when_file_absent(tmp_path):
    with pytest.raises(RuntimeError, match="not found"):
        read_boot_mapping(str(tmp_path / "missing.json"))


def test_read_boot_mapping_raises_when_file_is_malformed(tmp_path):
    path = tmp_path / "aura-boot.json"
    path.write_text("{not valid json")

    with pytest.raises(json.JSONDecodeError):
        read_boot_mapping(str(path))


def test_read_boot_mapping_ignores_old_aura_settings_json_and_names_aura_boot_json_when_absent(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "aura-settings.json").write_text(json.dumps({"default_scene": "tag"}))

    with pytest.raises(RuntimeError, match=r"aura-boot\.json"):
        read_boot_mapping()

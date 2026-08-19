"""Loader for aura-settings.json — no board imports, CPython-testable."""

from __future__ import annotations

import json

__all__ = ["read_settings_mapping"]


def read_settings_mapping(path: str = "aura-settings.json") -> dict:
    """Return the raw settings mapping from the JSON file at *path*.

    Mirrors :func:`hardware.shared.device_config.read_device_config_mapping`:
    the same open/load/raise shape, kept separate rather than shared because
    the two files serve different concerns (hardware config vs. device
    settings).

    Raises:
        RuntimeError: If *path* does not exist. The device has no built-in
            default settings, so a settings file must be deployed to the
            board.
    """
    try:
        with open(path) as f:
            return json.load(f)
    except OSError:
        raise RuntimeError(f"{path} not found — deploy device settings to the board") from None

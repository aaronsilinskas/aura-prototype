"""Loader for aura-boot.json — no board imports, CPython-testable."""

from __future__ import annotations

import json

__all__ = ["read_boot_mapping"]


def read_boot_mapping(path: str = "aura-boot.json") -> dict:
    """Return the raw boot-values mapping from the JSON file at *path*.

    Mirrors :func:`hardware.shared.device_config.read_device_config_mapping`:
    the same open/load/raise shape, kept separate rather than shared because
    the two files serve different concerns (hardware config vs. boot values).

    Raises:
        RuntimeError: If *path* does not exist. The device has no built-in
            boot values, so the file must be deployed to the board.
    """
    try:
        with open(path) as f:
            return json.load(f)
    except OSError:
        raise RuntimeError(f"{path} not found — deploy boot values to the board") from None

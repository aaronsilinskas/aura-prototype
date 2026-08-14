"""Shared test helpers for hardware/circuitpython test modules.

Extracted from test_device_builder.py so the subsystem-cluster test modules
that split off from it can import the same ExitStack-based patch helpers,
config builders, and recording-logger factory from one place instead of
each re-deriving (or cross-importing from each other) where they should
live.
"""

from __future__ import annotations

import sys
from contextlib import ExitStack
from typing import NamedTuple
from unittest.mock import MagicMock, patch

from engine.log import Logger
from hardware.shared.device_config import parse_device_config


class _HwPatchMocks(NamedTuple):
    """The mocks `_enter_hw_patches` installed, so callers can assert on any of them."""

    i2c: MagicMock
    spi: MagicMock
    accelerometer: MagicMock | None
    magnetometer: MagicMock | None
    drv2605: MagicMock | None
    radio: MagicMock | None
    sdcard: MagicMock | None


def _enter_hw_patches(
    stack: ExitStack,
    own_i2c: object | None = None,
    own_spi: object | None = None,
    patch_drv2605: bool = True,
    patch_accelerometer: bool = True,
    patch_magnetometer: bool = True,
    patch_radio: bool = True,
    patch_sdcard: bool = True,
) -> _HwPatchMocks:
    """Enter patches for all CircuitPython hardware setup helpers.

    Returns the patched mocks so callers can assert on them (e.g. whether
    ``_setup_i2c`` was invoked at all). *own_i2c*/*own_spi* are the buses
    they return when build_hardware constructs them itself. *patch_drv2605*,
    *patch_accelerometer*, *patch_magnetometer*, *patch_radio*, and
    *patch_sdcard* are False for tests that need ``_setup_drv2605``,
    ``_setup_accelerometer``, ``_setup_magnetometer``, ``_setup_radio``, or
    ``_setup_sdcard`` to run for real (e.g. hitting their own ImportError
    probes) — their mock is then `None`.
    """
    mock_setup_i2c = stack.enter_context(
        patch(
            "hardware.circuitpython.device_builder._setup_i2c",
            return_value=own_i2c if own_i2c is not None else MagicMock(),
        )
    )
    mock_setup_spi = stack.enter_context(
        patch(
            "hardware.circuitpython.device_builder._setup_spi",
            return_value=own_spi if own_spi is not None else MagicMock(),
        )
    )
    stack.enter_context(
        patch("hardware.circuitpython.device_builder._setup_buttons", return_value=MagicMock())
    )
    mock_setup_accelerometer = None
    if patch_accelerometer:
        mock_setup_accelerometer = stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_accelerometer", return_value=None)
        )
    mock_setup_magnetometer = None
    if patch_magnetometer:
        mock_setup_magnetometer = stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_magnetometer", return_value=None)
        )
    mock_setup_drv2605 = None
    if patch_drv2605:
        mock_setup_drv2605 = stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_drv2605", return_value=None)
        )
    mock_setup_radio = None
    if patch_radio:
        mock_setup_radio = stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_radio", return_value=None)
        )
    mock_setup_sdcard = None
    if patch_sdcard:
        mock_setup_sdcard = stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_sdcard", return_value=None)
        )
    return _HwPatchMocks(
        mock_setup_i2c,
        mock_setup_spi,
        mock_setup_accelerometer,
        mock_setup_magnetometer,
        mock_setup_drv2605,
        mock_setup_radio,
        mock_setup_sdcard,
    )


def _patch_neopixel(stack: ExitStack) -> MagicMock:
    """Patch the lazily-imported ``neopixel`` module and stub ``NeoPixel()``.

    Returns the mock module so callers can assert on ``NeoPixel`` calls.
    """
    mock_neopixel = MagicMock()
    stack.enter_context(patch.dict(sys.modules, {"neopixel": mock_neopixel}))
    mock_neopixel.NeoPixel.return_value = MagicMock()
    return mock_neopixel


def _mock_board(**pins):
    """Return a mock board module with the given pin attributes."""
    mock = MagicMock()
    for name, pin in pins.items():
        setattr(mock, name, pin)
    return mock


def _matrix_config(brightness: float | None = None, address: int | None = None):
    """Return a DeviceConfig with pixels.type='matrix'."""
    pixels_entry = {
        "type": "matrix",
        "cols": 13,
        "scope_rows": {
            "global.buff": [0, 1],
            "global.debuff": [1, 2],
            "global.main": [2, 5],
            "personal": [5, 7],
            "directional": [7, 8],
            "ambient": [8, 9],
        },
    }
    if brightness is not None:
        pixels_entry["brightness"] = brightness
    if address is not None:
        pixels_entry["address"] = address
    mapping = {
        "pixels": [pixels_entry],
        "buttons": ["D9", "D10"],
    }
    return parse_device_config(mapping)


def _neopixel_config(scopes: dict | None = None):
    """Return a DeviceConfig with pixels.type='neopixel'."""
    if scopes is None:
        scopes = {
            "personal": {"pin": "D5", "count": 10},
            "directional": {"pin": "D6", "count": 4},
        }
    mapping = {
        "pixels": [{"type": "neopixel", "scopes": scopes}],
        "buttons": ["D9"],
    }
    return parse_device_config(mapping)


def _minimal_config():
    """Return a DeviceConfig declaring buttons but no optional sections at all."""
    return parse_device_config({"buttons": ["D9"]})


def _recording_logger(tag: str = "[hw]") -> tuple[Logger, list[str]]:
    """Return a Logger wired to an in-memory sink, plus the fragments it records.

    Mirrors ``engine.tests.test_log``'s own helper -- the recording-sink
    pattern established there for asserting a logger's exact emitted line
    sequence.
    """
    fragments: list[str] = []
    return Logger(tag=tag, sink=fragments.append), fragments

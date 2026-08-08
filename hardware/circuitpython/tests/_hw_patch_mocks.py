"""Shared hardware-patch mock helpers for hardware/circuitpython test modules.

Extracted from test_device_builder.py so the subsystem-cluster test modules
that split off from it can import the same ExitStack-based patch helpers
instead of each re-deriving where they should live.
"""

from __future__ import annotations

import sys
from contextlib import ExitStack
from typing import NamedTuple
from unittest.mock import MagicMock, patch


class _HwPatchMocks(NamedTuple):
    """The mocks `_enter_hw_patches` installed, so callers can assert on any of them."""

    i2c: MagicMock
    spi: MagicMock
    accelerometer: MagicMock | None
    drv2605: MagicMock | None
    radio: MagicMock | None


def _enter_hw_patches(
    stack: ExitStack,
    own_i2c: object | None = None,
    own_spi: object | None = None,
    patch_drv2605: bool = True,
    patch_accelerometer: bool = True,
    patch_radio: bool = True,
) -> _HwPatchMocks:
    """Enter patches for all CircuitPython hardware setup helpers.

    Returns the patched mocks so callers can assert on them (e.g. whether
    ``_setup_i2c`` was invoked at all). *own_i2c*/*own_spi* are the buses
    they return when build_hardware constructs them itself. *patch_drv2605*,
    *patch_accelerometer*, and *patch_radio* are False for tests that need
    ``_setup_drv2605``, ``_setup_accelerometer``, or ``_setup_radio`` to run
    for real (e.g. hitting their own ImportError probes) — their mock is
    then `None`.
    """
    stack.enter_context(patch("hardware.circuitpython.device_builder._setup_external_power"))
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
    return _HwPatchMocks(
        mock_setup_i2c,
        mock_setup_spi,
        mock_setup_accelerometer,
        mock_setup_drv2605,
        mock_setup_radio,
    )


def _patch_neopixel(stack: ExitStack) -> MagicMock:
    """Patch the lazily-imported ``neopixel`` module and stub ``NeoPixel()``.

    Returns the mock module so callers can assert on ``NeoPixel`` calls.
    """
    mock_neopixel = MagicMock()
    stack.enter_context(patch.dict(sys.modules, {"neopixel": mock_neopixel}))
    mock_neopixel.NeoPixel.return_value = MagicMock()
    return mock_neopixel

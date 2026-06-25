"""Tests for device_builder.build_hardware — NeoPixel branch.

Verifies that build_hardware produces a NeoPixelEffectOutput (not a matrix
output) when the config selects pixels.type = 'neopixel'.  All hardware
modules (board, busio, propmaker) are injected or patched so this suite
runs under CPython.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from hardware.shared.device_config import (
    parse_device_config,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _neopixel_config(scopes: dict | None = None):
    """Return a DeviceConfig with pixels.type='neopixel'."""
    if scopes is None:
        scopes = {
            "personal": {"pin": "D5", "count": 10},
            "directional": {"pin": "D6", "count": 4},
        }
    mapping = {
        "pixels": {"type": "neopixel", "scopes": scopes},
        "buttons": ["D9"],
    }
    return parse_device_config(mapping)


def _mock_board(**pins):
    """Return a mock board module with the given pin attributes."""
    mock = MagicMock()
    for name, pin in pins.items():
        setattr(mock, name, pin)
    return mock


# ---------------------------------------------------------------------------
# build_hardware produces NeoPixelEffectOutput for neopixel config
# ---------------------------------------------------------------------------


def test_build_hardware_neopixel_returns_neopixel_effect_output() -> None:
    """build_hardware produces a NeoPixelEffectOutput when pixels.type='neopixel'."""
    from hardware.circuitpython.neopixel_output import NeoPixelEffectOutput

    config = _neopixel_config()
    board_mock = _mock_board(D5=MagicMock(), D6=MagicMock(), D9=MagicMock())

    with (
        patch("hardware.circuitpython.device_builder.propmaker") as mock_pm,
        patch("hardware.circuitpython.device_builder.neopixel") as mock_neopixel,
    ):
        mock_pm.setup_external_power.return_value = None
        mock_pm.setup_i2c.return_value = MagicMock()
        mock_pm.setup_accelerometer.return_value = None
        mock_pm.setup_drv2605.return_value = None
        mock_pm.setup_buttons.return_value = MagicMock()
        mock_neopixel.NeoPixel.return_value = MagicMock()

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    pixel_outputs = [o for o in hw.outputs if isinstance(o, NeoPixelEffectOutput)]
    assert len(pixel_outputs) == 1


def test_build_hardware_neopixel_output_has_correct_scopes() -> None:
    """NeoPixelEffectOutput produced by build_hardware declares the configured scopes."""
    from hardware.circuitpython.neopixel_output import NeoPixelEffectOutput

    config = _neopixel_config()
    board_mock = _mock_board(D5=MagicMock(), D6=MagicMock(), D9=MagicMock())

    with (
        patch("hardware.circuitpython.device_builder.propmaker") as mock_pm,
        patch("hardware.circuitpython.device_builder.neopixel") as mock_neopixel,
    ):
        mock_pm.setup_external_power.return_value = None
        mock_pm.setup_i2c.return_value = MagicMock()
        mock_pm.setup_accelerometer.return_value = None
        mock_pm.setup_drv2605.return_value = None
        mock_pm.setup_buttons.return_value = MagicMock()
        mock_neopixel.NeoPixel.return_value = MagicMock()

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    output = next(o for o in hw.outputs if isinstance(o, NeoPixelEffectOutput))
    scope_keys = {sv.keys[0] for sv in output.scopes}
    assert scope_keys == {"personal", "directional"}


def test_build_hardware_neopixel_output_resolves_pin_names() -> None:
    """build_hardware resolves each scope's pin name from the board module."""
    d5_pin = MagicMock(name="D5")
    d6_pin = MagicMock(name="D6")
    board_mock = _mock_board(D5=d5_pin, D6=d6_pin, D9=MagicMock())

    config = _neopixel_config()

    with (
        patch("hardware.circuitpython.device_builder.propmaker") as mock_pm,
        patch("hardware.circuitpython.device_builder.neopixel") as mock_neopixel,
    ):
        mock_pm.setup_external_power.return_value = None
        mock_pm.setup_i2c.return_value = MagicMock()
        mock_pm.setup_accelerometer.return_value = None
        mock_pm.setup_drv2605.return_value = None
        mock_pm.setup_buttons.return_value = MagicMock()
        mock_neopixel.NeoPixel.return_value = MagicMock()

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock)

    # neopixel.NeoPixel must have been called with each resolved pin
    called_pins = {c.args[0] for c in mock_neopixel.NeoPixel.call_args_list}
    assert d5_pin in called_pins
    assert d6_pin in called_pins


def test_build_hardware_neopixel_strips_constructed_with_auto_write_false() -> None:
    """build_hardware constructs each NeoPixel strip with auto_write=False.

    auto_write=False ensures flush() drives all hardware writes rather than
    every pixel assignment triggering an immediate SPI/UART transaction.
    """
    config = _neopixel_config()
    board_mock = _mock_board(D5=MagicMock(), D6=MagicMock(), D9=MagicMock())

    with (
        patch("hardware.circuitpython.device_builder.propmaker") as mock_pm,
        patch("hardware.circuitpython.device_builder.neopixel") as mock_neopixel,
    ):
        mock_pm.setup_external_power.return_value = None
        mock_pm.setup_i2c.return_value = MagicMock()
        mock_pm.setup_accelerometer.return_value = None
        mock_pm.setup_drv2605.return_value = None
        mock_pm.setup_buttons.return_value = MagicMock()
        mock_neopixel.NeoPixel.return_value = MagicMock()

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock)

    for call_kwargs in mock_neopixel.NeoPixel.call_args_list:
        assert call_kwargs.kwargs.get("auto_write") is False, (
            "Each NeoPixel strip must be constructed with auto_write=False"
        )


def test_build_hardware_neopixel_raises_on_unknown_pin() -> None:
    """build_hardware raises ValueError when a scope pin does not exist on the board."""
    config = _neopixel_config(
        scopes={"personal": {"pin": "NONEXISTENT_PIN", "count": 5}},
    )
    board_mock = MagicMock(spec=[])  # no attributes → AttributeError on getattr

    with (
        patch("hardware.circuitpython.device_builder.propmaker") as mock_pm,
        patch("hardware.circuitpython.device_builder.neopixel"),
    ):
        mock_pm.setup_external_power.return_value = None
        mock_pm.setup_i2c.return_value = MagicMock()
        mock_pm.setup_accelerometer.return_value = None
        mock_pm.setup_drv2605.return_value = None
        mock_pm.setup_buttons.return_value = MagicMock()

        from hardware.circuitpython.device_builder import build_hardware

        with pytest.raises(ValueError, match="NONEXISTENT_PIN"):
            build_hardware(config, board_module=board_mock)

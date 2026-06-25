"""Tests for device_builder.build_hardware — matrix, NeoPixel, audio, motor, and IR branches.

Verifies that build_hardware produces the correct EffectOutput for each
pixels.type (matrix and neopixel) and that audio, DRV2605 motor, and IR
paths wire up correctly.  All hardware modules (board, busio, pulseio,
digitalio) are patched so this suite runs under CPython.
"""

from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest

from hardware.shared.device_config import (
    parse_device_config,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _matrix_config():
    """Return a DeviceConfig with pixels.type='matrix'."""
    mapping = {
        "pixels": [
            {
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
        ],
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


def _mock_board(**pins):
    """Return a mock board module with the given pin attributes."""
    mock = MagicMock()
    for name, pin in pins.items():
        setattr(mock, name, pin)
    return mock


def _enter_hw_patches(stack: ExitStack) -> None:
    """Enter patches for all CircuitPython hardware setup helpers."""
    stack.enter_context(patch("hardware.circuitpython.device_builder._setup_external_power"))
    stack.enter_context(
        patch("hardware.circuitpython.device_builder._setup_i2c", return_value=MagicMock())
    )
    stack.enter_context(
        patch("hardware.circuitpython.device_builder._setup_buttons", return_value=MagicMock())
    )
    stack.enter_context(
        patch("hardware.circuitpython.device_builder._setup_accelerometer", return_value=None)
    )
    stack.enter_context(
        patch("hardware.circuitpython.device_builder._setup_drv2605", return_value=None)
    )


# ---------------------------------------------------------------------------
# build_hardware produces IS31FL3741EffectOutput for matrix config
# ---------------------------------------------------------------------------


def test_build_hardware_matrix_produces_one_is31fl3741_output() -> None:
    from hardware.circuitpython.is31fl3741_output import IS31FL3741EffectOutput

    config = _matrix_config()
    board_mock = _mock_board(D9=MagicMock(), D10=MagicMock())

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_matrix_is31fl3741",
                return_value=MagicMock(),
            )
        )

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    matrix_outputs = [o for o in hw.outputs if isinstance(o, IS31FL3741EffectOutput)]
    assert len(matrix_outputs) == 1


def test_build_hardware_matrix_output_resolution_matches_config_cols() -> None:
    from hardware.circuitpython.is31fl3741_output import IS31FL3741EffectOutput

    config = _matrix_config()
    board_mock = _mock_board(D9=MagicMock(), D10=MagicMock())

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_matrix_is31fl3741",
                return_value=MagicMock(),
            )
        )

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    matrix_output = next(o for o in hw.outputs if isinstance(o, IS31FL3741EffectOutput))
    assert matrix_output.min_resolution == 13


def test_build_hardware_matrix_output_can_create_buffer_for_configured_scope() -> None:
    from hardware.circuitpython.is31fl3741_output import IS31FL3741EffectOutput

    config = _matrix_config()
    board_mock = _mock_board(D9=MagicMock(), D10=MagicMock())

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_matrix_is31fl3741",
                return_value=MagicMock(),
            )
        )

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    matrix_output = next(o for o in hw.outputs if isinstance(o, IS31FL3741EffectOutput))
    # create_buffer raises KeyError if scope_rows was not passed correctly
    buf = matrix_output.create_buffer("personal")
    assert buf is not None


# ---------------------------------------------------------------------------
# build_hardware produces NeoPixelEffectOutput for neopixel config
# ---------------------------------------------------------------------------


def test_build_hardware_neopixel_produces_one_output_per_scope() -> None:
    from hardware.circuitpython.neopixel_output import NeoPixelEffectOutput

    config = _neopixel_config()
    board_mock = _mock_board(D5=MagicMock(), D6=MagicMock(), D9=MagicMock())

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        mock_neopixel = stack.enter_context(patch("hardware.circuitpython.device_builder.neopixel"))
        mock_neopixel.NeoPixel.return_value = MagicMock()

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    pixel_outputs = [o for o in hw.outputs if isinstance(o, NeoPixelEffectOutput)]
    assert len(pixel_outputs) == 2


def test_build_hardware_neopixel_each_output_declares_one_scope() -> None:
    from hardware.circuitpython.neopixel_output import NeoPixelEffectOutput

    config = _neopixel_config()
    board_mock = _mock_board(D5=MagicMock(), D6=MagicMock(), D9=MagicMock())

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        mock_neopixel = stack.enter_context(patch("hardware.circuitpython.device_builder.neopixel"))
        mock_neopixel.NeoPixel.return_value = MagicMock()

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    pixel_outputs = [o for o in hw.outputs if isinstance(o, NeoPixelEffectOutput)]
    all_scope_keys = {sv.keys[0] for o in pixel_outputs for sv in o.scopes}
    assert all_scope_keys == {"personal", "directional"}
    for o in pixel_outputs:
        assert len(o.scopes) == 1


def test_build_hardware_neopixel_output_resolves_pin_names() -> None:
    d5_pin = MagicMock(name="D5")
    d6_pin = MagicMock(name="D6")
    board_mock = _mock_board(D5=d5_pin, D6=d6_pin, D9=MagicMock())

    config = _neopixel_config()

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        mock_neopixel = stack.enter_context(patch("hardware.circuitpython.device_builder.neopixel"))
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

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        mock_neopixel = stack.enter_context(patch("hardware.circuitpython.device_builder.neopixel"))
        mock_neopixel.NeoPixel.return_value = MagicMock()

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock)

    for call_kwargs in mock_neopixel.NeoPixel.call_args_list:
        assert call_kwargs.kwargs.get("auto_write") is False, (
            "Each NeoPixel strip must be constructed with auto_write=False"
        )


def test_build_hardware_neopixel_raises_on_unknown_pin() -> None:
    config = _neopixel_config(
        scopes={"personal": {"pin": "NONEXISTENT_PIN", "count": 5}},
    )
    board_mock = MagicMock(spec=[])  # no attributes → AttributeError on getattr

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        stack.enter_context(patch("hardware.circuitpython.device_builder.neopixel"))

        from hardware.circuitpython.device_builder import build_hardware

        with pytest.raises(ValueError, match="NONEXISTENT_PIN"):
            build_hardware(config, board_module=board_mock)


# ---------------------------------------------------------------------------
# build_hardware wires audio output when config.audio is present
# ---------------------------------------------------------------------------


def _neopixel_config_with_audio():
    """Return a DeviceConfig with a neopixel pixels section and audio config."""
    mapping = {
        "pixels": [{"type": "neopixel", "scopes": {"personal": {"pin": "D5", "count": 10}}}],
        "buttons": ["D9"],
        "audio": {
            "voices": 1,
            "max_volume": 0.5,
            "clips": {"hit": "/sounds/hit.wav"},
        },
    }
    return parse_device_config(mapping)


def test_build_hardware_audio_config_adds_audio_effect_output() -> None:
    from hardware.circuitpython.audio_output import AudioEffectOutput

    config = _neopixel_config_with_audio()
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())
    board_mock.I2S_BIT_CLOCK = MagicMock()
    board_mock.I2S_WORD_SELECT = MagicMock()
    board_mock.I2S_DATA = MagicMock()

    mock_audio_output = MagicMock(spec=AudioEffectOutput)

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        mock_neopixel = stack.enter_context(patch("hardware.circuitpython.device_builder.neopixel"))
        mock_neopixel.NeoPixel.return_value = MagicMock()
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder.AudioEffectOutput",
                return_value=mock_audio_output,
            )
        )

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    audio_outputs = [o for o in hw.outputs if isinstance(o, AudioEffectOutput)]
    assert len(audio_outputs) == 1


# ---------------------------------------------------------------------------
# build_hardware wires motor output when _setup_drv2605 returns a driver
# ---------------------------------------------------------------------------


def test_build_hardware_drv2605_motor_adds_drv2605_effect_output() -> None:
    from hardware.circuitpython.drv2605_output import Drv2605EffectOutput

    config = _neopixel_config()
    board_mock = _mock_board(D5=MagicMock(), D6=MagicMock(), D9=MagicMock())
    mock_motor = MagicMock()

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        # Override the drv2605 patch set in _enter_hw_patches to return a mock motor
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_drv2605",
                return_value=mock_motor,
            )
        )
        mock_neopixel = stack.enter_context(patch("hardware.circuitpython.device_builder.neopixel"))
        mock_neopixel.NeoPixel.return_value = MagicMock()

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    motor_outputs = [o for o in hw.outputs if isinstance(o, Drv2605EffectOutput)]
    assert len(motor_outputs) == 1


# ---------------------------------------------------------------------------
# build_hardware sets hw.ir_receiver when config.ir is present
# ---------------------------------------------------------------------------


def _neopixel_config_with_ir():
    """Return a DeviceConfig with a neopixel pixels section and IR config."""
    mapping = {
        "pixels": [{"type": "neopixel", "scopes": {"personal": {"pin": "D5", "count": 10}}}],
        "buttons": ["D9"],
        "ir": {
            "rx": "D11",
            "line": "D12",
        },
    }
    return parse_device_config(mapping)


def test_build_hardware_ir_config_sets_ir_receiver() -> None:
    config = _neopixel_config_with_ir()
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock(), D11=MagicMock(), D12=MagicMock())
    mock_receiver = MagicMock()

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        mock_neopixel = stack.enter_context(patch("hardware.circuitpython.device_builder.neopixel"))
        mock_neopixel.NeoPixel.return_value = MagicMock()
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_ir",
                return_value=({}, mock_receiver),
            )
        )

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    assert hw.ir_receiver is not None

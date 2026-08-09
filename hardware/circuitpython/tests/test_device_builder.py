"""Tests for device_builder.build_hardware — the core, cross-subsystem tests
that don't belong to any one subsystem cluster.

Covers output ordering across multiple components (pixels outputs preceding
audio/haptic outputs) and that ``transmit_pump``/``network_controls`` are
the same HardwareNetworkControls instance (#608). Matrix (IS31FL3741) and
NeoPixel pixel-branch coverage (_setup_matrix_is31fl3741, _setup_neopixels,
_setup_pixels, _describe_pixel_entry, and the pixels-specific build_hardware
ordering/narration tests) lives in test_device_builder_pixels.py (#776). I2C/
SPI/external-power bus setup (_setup_i2c, open_config_i2c, _setup_spi,
_setup_external_power, the caller-supplied-vs-self-constructed I2C bus tests,
and their build_hardware narration) lives in test_device_builder_buses_power.py
(#777). Audio (_setup_audio), haptics (_setup_drv2605), and accelerometer
build_hardware coverage -- including their "declared but bus unreachable" and
chip-not-found hard-error cases and their narration -- lives in
test_device_builder_audio_haptics.py (#778). Radio (_setup_radio) and the
build_hardware-level slice of IR (_describe_ir, hw.ir_receiver wiring, and
their narration) live in test_device_builder_radio_ir.py (#779). Buttons
(_setup_buttons, _describe_buttons) and build_hardware's cross-cutting
narration spine (the opening banner/external-power/i2c/spi/buttons/closing-
summary lines, minimal-config narration, and the no-logger-injected case)
live in test_device_builder_buttons_logging.py (#780); this file still uses a
neopixel-plus-audio-plus-haptics config as a vehicle for one piece of
non-pixel/non-bus/non-audio-haptics/non-radio/non-ir/non-buttons coverage
that spans pixels, audio, and haptics (pixels outputs preceding audio/haptic
outputs). All hardware modules (board, busio, pulseio, digitalio) are patched
so this suite runs under CPython.
"""

from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from hardware.circuitpython.tests._hw_patch_mocks import (
    _enter_hw_patches,
    _mock_board,
    _neopixel_config,
    _patch_neopixel,
)
from hardware.shared.device_config import (
    parse_device_config,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def test_build_hardware_pixels_outputs_precede_audio_and_haptic_outputs() -> None:
    """build_hardware appends pixels outputs before audio and haptic outputs,
    regardless of how many pixel outputs _setup_pixels returns — ordering
    that scene_runtime and the pixel profiler rely on staying stable."""
    from hardware.circuitpython.audio_output import AudioEffectOutput
    from hardware.circuitpython.drv2605_output import Drv2605EffectOutput
    from hardware.circuitpython.neopixel_output import NeoPixelEffectOutput

    mapping = {
        "pixels": [{"type": "neopixel", "scopes": {"personal": {"pin": "D5", "count": 10}}}],
        "buttons": ["D9"],
        "audio": {
            "voices": 1,
            "max_volume": 0.5,
            "clips": {"hit": "/sounds/hit.wav"},
            "i2s_bit_clock": "I2S_BIT_CLOCK",
            "i2s_word_select": "I2S_WORD_SELECT",
            "i2s_data": "I2S_DATA",
        },
        "haptics": {},
    }
    config = parse_device_config(mapping)
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())
    board_mock.I2S_BIT_CLOCK = MagicMock()
    board_mock.I2S_WORD_SELECT = MagicMock()
    board_mock.I2S_DATA = MagicMock()
    mock_driver = MagicMock()

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_drv2605",
                return_value=mock_driver,
            )
        )
        _patch_neopixel(stack)
        stack.enter_context(
            patch(
                "hardware.circuitpython.audio_output.AudioEffectOutput",
                return_value=MagicMock(spec=AudioEffectOutput),
            )
        )

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    pixels_index = next(i for i, o in enumerate(hw.outputs) if isinstance(o, NeoPixelEffectOutput))
    audio_index = next(i for i, o in enumerate(hw.outputs) if isinstance(o, AudioEffectOutput))
    haptic_index = next(i for i, o in enumerate(hw.outputs) if isinstance(o, Drv2605EffectOutput))
    assert pixels_index < audio_index < haptic_index


# ---------------------------------------------------------------------------
# build_hardware wires transmit_pump and network_controls to the same
# HardwareNetworkControls instance (issue #608)
# ---------------------------------------------------------------------------


def test_build_hardware_transmit_pump_is_same_object_as_network_controls() -> None:
    config = _neopixel_config()
    board_mock = _mock_board(D5=MagicMock(), D6=MagicMock(), D9=MagicMock())

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    assert hw.transmit_pump is hw.network_controls


def test_build_hardware_transmit_pump_satisfies_transmit_pump() -> None:
    from engine.network import TransmitPump

    config = _neopixel_config()
    board_mock = _mock_board(D5=MagicMock(), D6=MagicMock(), D9=MagicMock())

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    assert isinstance(hw.transmit_pump, TransmitPump)

"""Tests for device_builder.build_hardware — the core, cross-subsystem tests
that don't belong to any one subsystem cluster: output ordering across
multiple components, that ``transmit_pump``/``network_controls`` are the
same HardwareNetworkControls instance (#608), and the
``_construct_with_optional_address`` helper shared by the accelerometer,
magnetometer, and haptics ``_setup_*`` functions (#843). Per-subsystem
coverage (pixels, buses/power, audio/haptics, radio/ir, buttons/logging)
lives in the sibling test_device_builder_*.py files split out under #767;
shared config/patch helpers come from _hw_patch_mocks.py.
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
# _construct_with_optional_address — the shared address branch every bare I2C
# device constructor (accelerometer, magnetometer, haptics) forwards through
# (#843)
# ---------------------------------------------------------------------------


def test_construct_with_optional_address_omits_address_kwarg_when_none() -> None:
    """A None address means no override -- the driver's own default applies,
    so the construction call must not pass address= at all rather than
    passing address=None."""
    from hardware.circuitpython.device_builder import _construct_with_optional_address

    ctor = MagicMock()
    fake_i2c = MagicMock(name="i2c")

    result = _construct_with_optional_address(ctor, fake_i2c, None)

    ctor.assert_called_once_with(fake_i2c)
    assert result is ctor.return_value


def test_construct_with_optional_address_forwards_configured_address() -> None:
    from hardware.circuitpython.device_builder import _construct_with_optional_address

    ctor = MagicMock()
    fake_i2c = MagicMock(name="i2c")

    result = _construct_with_optional_address(ctor, fake_i2c, 0x19)

    ctor.assert_called_once_with(fake_i2c, address=0x19)
    assert result is ctor.return_value


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

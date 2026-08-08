"""Tests for device_builder.build_hardware — audio, haptic, accelerometer,
radio, and IR branches, plus the general logger spine.

Verifies that build_hardware wires up audio, the DRV2605 haptic driver,
accelerometer, radio, and IR correctly -- gating each on i2c/spi bus
availability where relevant -- and narrates each step through its injected
logger. Matrix (IS31FL3741) and NeoPixel pixel-branch coverage
(_setup_matrix_is31fl3741, _setup_neopixels, _setup_pixels,
_describe_pixel_entry, and the pixels-specific build_hardware ordering/
narration tests) lives in test_device_builder_pixels.py (#776). I2C/SPI/
external-power bus setup (_setup_i2c, open_config_i2c, _setup_spi,
_setup_external_power, the caller-supplied-vs-self-constructed I2C bus tests,
and their build_hardware narration) lives in test_device_builder_buses_power.py
(#777) — this file still uses matrix/neopixel configs as a vehicle for
non-pixel/non-bus coverage (e.g. output ordering relative to audio/haptics)
and still covers the accelerometer/haptics/radio "declared but bus
unreachable" hard-error cases, since those exercise the accelerometer/
haptics/radio subsystems, not the bus setup itself. All hardware modules
(board, busio, pulseio, digitalio) are patched so this suite runs under
CPython.
"""

from __future__ import annotations

import io
import re
import sys
from contextlib import ExitStack, redirect_stdout
from unittest.mock import MagicMock, patch

import pytest

from engine.log import Logger
from engine.network import AREA_OF_EFFECT, CONE, LINE
from hardware.circuitpython.tests._hw_patch_mocks import (
    _enter_hw_patches,
    _patch_neopixel,
)
from hardware.shared.device_config import (
    parse_device_config,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _matrix_config(brightness: float | None = None):
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


def _mock_board(**pins):
    """Return a mock board module with the given pin attributes."""
    mock = MagicMock()
    for name, pin in pins.items():
        setattr(mock, name, pin)
    return mock


def _recording_logger(tag: str = "[hw]") -> tuple[Logger, list[str]]:
    """Return a Logger wired to an in-memory sink, plus the fragments it records.

    Mirrors ``engine.tests.test_log``'s own helper -- the recording-sink
    pattern established there for asserting a logger's exact emitted line
    sequence.
    """
    fragments: list[str] = []
    return Logger(tag=tag, sink=fragments.append), fragments


def _minimal_config():
    """Return a DeviceConfig declaring buttons but no optional sections at all."""
    return parse_device_config({"buttons": ["D9"]})


# ---------------------------------------------------------------------------
# _setup_audio — construct AudioRegistry + AudioEffectOutput from AudioConfig
# ---------------------------------------------------------------------------


def _audio_config(**overrides):
    """Return an AudioConfig, defaulting to one voice, half volume, one clip."""
    mapping = {
        "voices": 1,
        "max_volume": 0.5,
        "clips": {"hit": "/sounds/hit.wav"},
        "i2s_bit_clock": "I2S_BIT_CLOCK",
        "i2s_word_select": "I2S_WORD_SELECT",
        "i2s_data": "I2S_DATA",
    }
    mapping.update(overrides)
    return parse_device_config(
        {
            "pixels": [{"type": "neopixel", "scopes": {"personal": {"pin": "D5", "count": 10}}}],
            "buttons": ["D9"],
            "audio": mapping,
        }
    ).audio


def test_setup_audio_returns_the_constructed_audio_effect_output() -> None:
    from hardware.circuitpython.audio_output import AudioEffectOutput

    audio_cfg = _audio_config()
    board_mock = _mock_board(
        I2S_BIT_CLOCK=MagicMock(), I2S_WORD_SELECT=MagicMock(), I2S_DATA=MagicMock()
    )

    mock_audio_output = MagicMock(spec=AudioEffectOutput)

    with ExitStack() as stack:
        stack.enter_context(
            patch(
                "hardware.circuitpython.audio_output.AudioEffectOutput",
                return_value=mock_audio_output,
            )
        )

        from hardware.circuitpython.device_builder import _setup_audio

        result = _setup_audio(audio_cfg, board_mock)

    assert result is mock_audio_output


def test_setup_audio_resolves_i2s_pins_named_in_audio_config() -> None:
    """I2S pins are sourced from AudioConfig's i2s_* fields, not a fixed
    board.I2S_* attribute name — a board can name them anything."""
    bit_clock = MagicMock(name="bit_clock")
    word_select = MagicMock(name="word_select")
    data = MagicMock(name="data")
    audio_cfg = _audio_config(i2s_bit_clock="GP10", i2s_word_select="GP11", i2s_data="GP12")
    board_mock = _mock_board(GP10=bit_clock, GP11=word_select, GP12=data)

    with ExitStack() as stack:
        mock_audio_cls = stack.enter_context(
            patch("hardware.circuitpython.audio_output.AudioEffectOutput")
        )

        from hardware.circuitpython.device_builder import _setup_audio

        _setup_audio(audio_cfg, board_mock)

    kwargs = mock_audio_cls.call_args.kwargs
    assert kwargs["i2s_bit_clock"] is bit_clock
    assert kwargs["i2s_word_select"] is word_select
    assert kwargs["i2s_data"] is data


def test_setup_audio_unknown_i2s_pin_name_raises_pin_not_found_value_error() -> None:
    audio_cfg = _audio_config(i2s_bit_clock="NONEXISTENT_PIN")
    board_mock = MagicMock(spec=[])  # no attributes → AttributeError on getattr

    from hardware.circuitpython.device_builder import _setup_audio

    with pytest.raises(ValueError, match="NONEXISTENT_PIN"):
        _setup_audio(audio_cfg, board_mock)


def test_setup_audio_forwards_configured_max_volume() -> None:
    audio_cfg = _audio_config(max_volume=0.75)
    board_mock = _mock_board(
        I2S_BIT_CLOCK=MagicMock(), I2S_WORD_SELECT=MagicMock(), I2S_DATA=MagicMock()
    )

    with ExitStack() as stack:
        mock_audio_cls = stack.enter_context(
            patch("hardware.circuitpython.audio_output.AudioEffectOutput")
        )

        from hardware.circuitpython.device_builder import _setup_audio

        _setup_audio(audio_cfg, board_mock)

    assert mock_audio_cls.call_args.kwargs["max_volume"] == 0.75


def test_setup_audio_forwards_configured_voice_count() -> None:
    audio_cfg = _audio_config(voices=3)
    board_mock = _mock_board(
        I2S_BIT_CLOCK=MagicMock(), I2S_WORD_SELECT=MagicMock(), I2S_DATA=MagicMock()
    )

    with ExitStack() as stack:
        mock_audio_cls = stack.enter_context(
            patch("hardware.circuitpython.audio_output.AudioEffectOutput")
        )

        from hardware.circuitpython.device_builder import _setup_audio

        _setup_audio(audio_cfg, board_mock)

    assert mock_audio_cls.call_args.kwargs["num_voices"] == 3


def test_setup_audio_registers_configured_clips_on_audio_registry() -> None:
    audio_cfg = _audio_config(clips={"hit": "/sounds/hit.wav", "miss": "/sounds/miss.wav"})
    board_mock = _mock_board(
        I2S_BIT_CLOCK=MagicMock(), I2S_WORD_SELECT=MagicMock(), I2S_DATA=MagicMock()
    )

    with ExitStack() as stack:
        mock_audio_cls = stack.enter_context(
            patch("hardware.circuitpython.audio_output.AudioEffectOutput")
        )

        from hardware.circuitpython.device_builder import _setup_audio

        _setup_audio(audio_cfg, board_mock)

    registry = mock_audio_cls.call_args.args[0]
    assert registry.path("hit") == "/sounds/hit.wav"
    assert registry.path("miss") == "/sounds/miss.wav"


# ---------------------------------------------------------------------------
# build_hardware wires audio output when config.audio is present
# ---------------------------------------------------------------------------


def _neopixel_config_with_audio(**audio_overrides):
    """Return a DeviceConfig with a neopixel pixels section and audio config.

    *audio_overrides* replace individual keys of the default audio mapping
    (one voice, half volume, one clip, ``I2S_*``-named pins) -- e.g. an
    unknown I2S pin name for narration-failure tests.
    """
    audio = {
        "voices": 1,
        "max_volume": 0.5,
        "clips": {"hit": "/sounds/hit.wav"},
        "i2s_bit_clock": "I2S_BIT_CLOCK",
        "i2s_word_select": "I2S_WORD_SELECT",
        "i2s_data": "I2S_DATA",
    }
    audio.update(audio_overrides)
    mapping = {
        "pixels": [{"type": "neopixel", "scopes": {"personal": {"pin": "D5", "count": 10}}}],
        "buttons": ["D9"],
        "audio": audio,
    }
    return parse_device_config(mapping)


def test_build_hardware_audio_config_adds_audio_effect_output() -> None:
    """build_hardware's audio wiring is a single delegating call to
    _setup_audio — construction details (registry, clips, I2S pins,
    max_volume, voices) are covered directly on _setup_audio; this only
    confirms the output reaches the bundle."""
    from hardware.circuitpython.audio_output import AudioEffectOutput

    config = _neopixel_config_with_audio()
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())
    board_mock.I2S_BIT_CLOCK = MagicMock()
    board_mock.I2S_WORD_SELECT = MagicMock()
    board_mock.I2S_DATA = MagicMock()

    mock_audio_output = MagicMock(spec=AudioEffectOutput)

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        _patch_neopixel(stack)
        stack.enter_context(
            patch(
                "hardware.circuitpython.audio_output.AudioEffectOutput",
                return_value=mock_audio_output,
            )
        )

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    audio_outputs = [o for o in hw.outputs if isinstance(o, AudioEffectOutput)]
    assert len(audio_outputs) == 1


def test_build_hardware_disabled_audio_section_omits_audio_output() -> None:
    """``audio: {enabled: false}`` is neither built nor probed (#692) --
    the config's neopixel pixels entry still builds, proving only audio
    was gated off."""
    from hardware.circuitpython.audio_output import AudioEffectOutput
    from hardware.circuitpython.neopixel_output import NeoPixelEffectOutput

    config = _neopixel_config_with_audio()
    config.audio.enabled = False
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    assert not any(isinstance(o, AudioEffectOutput) for o in hw.outputs)
    assert any(isinstance(o, NeoPixelEffectOutput) for o in hw.outputs)


# ---------------------------------------------------------------------------
# build_hardware — accelerometer is config-gated, not presence-probed (#691)
# ---------------------------------------------------------------------------


def _neopixel_config_with_accelerometer():
    """Return a DeviceConfig with a neopixel pixels section and an accelerometer section."""
    mapping = {
        "pixels": [{"type": "neopixel", "scopes": {"personal": {"pin": "D5", "count": 10}}}],
        "buttons": ["D9"],
        "accelerometer": {},
    }
    return parse_device_config(mapping)


def test_build_hardware_accelerometer_section_builds_accelerometer_onto_bundle() -> None:
    config = _neopixel_config_with_accelerometer()
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())
    mock_accelerometer = MagicMock()

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_accelerometer",
                return_value=mock_accelerometer,
            )
        )
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    assert hw.accelerometer is mock_accelerometer


def test_build_hardware_declared_accelerometer_with_no_i2c_bus_raises_runtime_error() -> None:
    """A declared accelerometer whose bus can't be reached is a hard error,
    mirroring the matrix-with-no-I2C-bus case — absence must be expressed by
    omitting the section, not a silent probe failure."""
    config = _neopixel_config_with_accelerometer()
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())

    with ExitStack() as stack:
        stack.enter_context(patch("hardware.circuitpython.device_builder._setup_external_power"))
        stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_i2c", return_value=None)
        )
        stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_buttons", return_value=MagicMock())
        )
        mock_setup_accelerometer = stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_accelerometer")
        )
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        with pytest.raises(RuntimeError, match="accelerometer"):
            build_hardware(config, board_module=board_mock)

    mock_setup_accelerometer.assert_not_called()


def test_build_hardware_declared_accelerometer_raises_when_chip_not_found() -> None:
    """A declared accelerometer whose chip can't be constructed on an available
    bus is a hard error too -- not just the no-I2C-bus case."""
    config = _neopixel_config_with_accelerometer()
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())

    with ExitStack() as stack:
        _enter_hw_patches(stack, patch_accelerometer=False)
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_accelerometer",
                side_effect=ValueError("no LIS3DH found"),
            )
        )
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        with pytest.raises(ValueError, match="no LIS3DH found"):
            build_hardware(config, board_module=board_mock)


def test_build_hardware_disabled_accelerometer_section_omits_accelerometer_from_bundle() -> None:
    """``accelerometer: {enabled: false}`` is neither built nor probed (#692)."""
    config = _neopixel_config_with_accelerometer()
    config.accelerometer.enabled = False
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())

    with ExitStack() as stack:
        mocks = _enter_hw_patches(stack)
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    assert hw.accelerometer is None
    mocks.accelerometer.assert_not_called()


def test_build_hardware_enabled_accelerometer_with_disabled_i2c_raises_runtime_error() -> None:
    """``i2c: {enabled: false}`` builds no bus at all, so an accelerometer
    left enabled hits the same declared-and-enabled-but-unreachable hard
    error as a missing i2c section (#692)."""
    mapping = {
        "pixels": [{"type": "neopixel", "scopes": {"personal": {"pin": "D5", "count": 10}}}],
        "buttons": ["D9"],
        "i2c": {"sda": "GP4", "scl": "GP5", "enabled": False},
        "accelerometer": {},
    }
    config = parse_device_config(mapping)
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())

    with ExitStack() as stack:
        stack.enter_context(patch("hardware.circuitpython.device_builder._setup_external_power"))
        stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_buttons", return_value=MagicMock())
        )
        mock_setup_accelerometer = stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_accelerometer")
        )
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        with pytest.raises(RuntimeError, match="accelerometer"):
            build_hardware(config, board_module=board_mock)

    mock_setup_accelerometer.assert_not_called()


# ---------------------------------------------------------------------------
# build_hardware — haptics is config-gated, not presence-probed (#691)
# ---------------------------------------------------------------------------


def _neopixel_config_with_haptics():
    """Return a DeviceConfig with a neopixel pixels section and a haptics section."""
    mapping = {
        "pixels": [{"type": "neopixel", "scopes": {"personal": {"pin": "D5", "count": 10}}}],
        "buttons": ["D9"],
        "haptics": {},
    }
    return parse_device_config(mapping)


def test_build_hardware_haptics_section_adds_drv2605_effect_output() -> None:
    from hardware.circuitpython.drv2605_output import Drv2605EffectOutput

    config = _neopixel_config_with_haptics()
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())
    mock_driver = MagicMock()

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        # Override the drv2605 patch set in _enter_hw_patches to return a mock driver
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_drv2605",
                return_value=mock_driver,
            )
        )
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    driver_outputs = [o for o in hw.outputs if isinstance(o, Drv2605EffectOutput)]
    assert len(driver_outputs) == 1


def test_build_hardware_declared_haptics_with_no_i2c_bus_raises_runtime_error() -> None:
    """A declared haptics section whose bus can't be reached is a hard error,
    mirroring the matrix-with-no-I2C-bus case."""
    config = _neopixel_config_with_haptics()
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())

    with ExitStack() as stack:
        stack.enter_context(patch("hardware.circuitpython.device_builder._setup_external_power"))
        stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_i2c", return_value=None)
        )
        stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_buttons", return_value=MagicMock())
        )
        mock_setup_drv2605 = stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_drv2605")
        )
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        with pytest.raises(RuntimeError, match="haptics"):
            build_hardware(config, board_module=board_mock)

    mock_setup_drv2605.assert_not_called()


def test_build_hardware_declared_haptics_raises_when_chip_not_found() -> None:
    """A declared haptics section whose chip can't be constructed on an
    available bus is a hard error too -- not just the no-I2C-bus case."""
    config = _neopixel_config_with_haptics()
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())

    with ExitStack() as stack:
        _enter_hw_patches(stack, patch_drv2605=False)
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_drv2605",
                side_effect=ValueError("no DRV2605 found"),
            )
        )
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        with pytest.raises(ValueError, match="no DRV2605 found"):
            build_hardware(config, board_module=board_mock)


def test_build_hardware_disabled_haptics_section_omits_haptic_output() -> None:
    """``haptics: {enabled: false}`` is neither built nor probed (#692)."""
    from hardware.circuitpython.drv2605_output import Drv2605EffectOutput

    config = _neopixel_config_with_haptics()
    config.haptics.enabled = False
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())

    with ExitStack() as stack:
        mocks = _enter_hw_patches(stack)
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    assert not any(isinstance(o, Drv2605EffectOutput) for o in hw.outputs)
    mocks.drv2605.assert_not_called()


# ---------------------------------------------------------------------------
# build_hardware -- radio is config-gated on spi, mirroring how the matrix,
# accelerometer, and haptics are config-gated on i2c (#703)
# ---------------------------------------------------------------------------


def _neopixel_config_with_radio():
    """Return a DeviceConfig with a neopixel pixels section, an spi section,
    and a radio section."""
    mapping = {
        "pixels": [{"type": "neopixel", "scopes": {"personal": {"pin": "D5", "count": 10}}}],
        "buttons": ["D9"],
        "spi": {"sck": "SCK", "mosi": "MOSI", "miso": "MISO"},
        "radio": {"cs": "D24", "reset": "D25", "frequency": 915.0, "node": 1},
    }
    return parse_device_config(mapping)


def test_build_hardware_radio_section_builds_radio_transport_onto_bundle() -> None:
    config = _neopixel_config_with_radio()
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())
    mock_transport = MagicMock(name="radio_transport")

    with ExitStack() as stack:
        _enter_hw_patches(stack, patch_radio=False)
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_radio",
                return_value=mock_transport,
            )
        )
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    assert hw.radio is mock_transport


def test_build_hardware_declared_radio_with_no_spi_bus_raises_runtime_error() -> None:
    """A declared radio whose SPI bus can't be reached is a hard error,
    mirroring the matrix-with-no-I2C-bus case -- absence must be expressed by
    omitting the section, not a silent probe failure."""
    config = _neopixel_config_with_radio()
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())

    with ExitStack() as stack:
        stack.enter_context(patch("hardware.circuitpython.device_builder._setup_external_power"))
        stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_i2c", return_value=MagicMock())
        )
        stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_spi", return_value=None)
        )
        stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_buttons", return_value=MagicMock())
        )
        mock_setup_radio = stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_radio")
        )
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        with pytest.raises(RuntimeError, match="radio"):
            build_hardware(config, board_module=board_mock)

    mock_setup_radio.assert_not_called()


def test_build_hardware_declared_radio_raises_when_chip_not_found() -> None:
    """A declared radio whose chip can't be constructed on an available bus
    is a hard error too -- not just the no-SPI-bus case."""
    config = _neopixel_config_with_radio()
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())

    with ExitStack() as stack:
        _enter_hw_patches(stack, patch_radio=False)
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_radio",
                side_effect=ValueError("no RFM69 found"),
            )
        )
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        with pytest.raises(ValueError, match="no RFM69 found"):
            build_hardware(config, board_module=board_mock)


def test_build_hardware_disabled_radio_section_omits_radio_from_bundle() -> None:
    """``radio: {enabled: false}`` is neither built nor probed, mirroring
    every other component's enabled toggle."""
    config = _neopixel_config_with_radio()
    config.radio.enabled = False
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())

    with ExitStack() as stack:
        mocks = _enter_hw_patches(stack)
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    assert hw.radio is None
    mocks.radio.assert_not_called()


def test_build_hardware_without_radio_section_leaves_radio_none() -> None:
    config = _neopixel_config()
    board_mock = _mock_board(D5=MagicMock(), D6=MagicMock(), D9=MagicMock())

    with ExitStack() as stack:
        mocks = _enter_hw_patches(stack)
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    assert hw.radio is None
    mocks.radio.assert_not_called()


# ---------------------------------------------------------------------------
# _setup_radio -- resolves radio pins and delegates to Rfm69RadioTransport
# ---------------------------------------------------------------------------


def test_setup_radio_wraps_resolved_pins_into_digitalinout_and_delegates_to_transport() -> None:
    radio_cfg = parse_device_config(
        {
            "buttons": [],
            "radio": {"cs": "D24", "reset": "D25", "frequency": 915.0, "node": 3},
        }
    ).radio
    cs_pin = MagicMock(name="cs_pin")
    reset_pin = MagicMock(name="reset_pin")
    board_mock = _mock_board(D24=cs_pin, D25=reset_pin)
    spi = MagicMock(name="spi")
    mock_transport = MagicMock(name="transport")

    with ExitStack() as stack:
        mock_digitalio = stack.enter_context(
            patch("hardware.circuitpython.device_builder.digitalio")
        )
        cs_dio = MagicMock(name="cs_dio")
        reset_dio = MagicMock(name="reset_dio")
        mock_digitalio.DigitalInOut.side_effect = [cs_dio, reset_dio]
        mock_transport_cls = stack.enter_context(
            patch(
                "hardware.circuitpython.rfm69_radio_transport.Rfm69RadioTransport",
                return_value=mock_transport,
            )
        )

        from hardware.circuitpython.device_builder import _setup_radio

        result = _setup_radio(spi, radio_cfg, board_mock)

    mock_digitalio.DigitalInOut.assert_any_call(cs_pin)
    mock_digitalio.DigitalInOut.assert_any_call(reset_pin)
    mock_transport_cls.assert_called_once_with(spi, cs_dio, reset_dio, 915.0, 3)
    assert result is mock_transport


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
# build_hardware — fully-loaded prop vs. accelerometer/haptics-less prop (#691)
# ---------------------------------------------------------------------------


def _fully_loaded_config_mapping() -> dict:
    """Raw mapping declaring every optional aura-device.json section: pixels
    (matrix + neopixel), buttons, ir, audio, i2c, accelerometer, and
    haptics."""
    return {
        "i2c": {"sda": "GP4", "scl": "GP5"},
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
            },
            {"type": "neopixel", "scopes": {"personal": {"pin": "D5", "count": 10}}},
        ],
        "buttons": ["D9"],
        "ir": {"rx": "D11", "line": "D12"},
        "audio": {
            "voices": 1,
            "max_volume": 0.5,
            "clips": {"hit": "/sounds/hit.wav"},
            "i2s_bit_clock": "I2S_BIT_CLOCK",
            "i2s_word_select": "I2S_WORD_SELECT",
            "i2s_data": "I2S_DATA",
        },
        "accelerometer": {},
        "haptics": {},
    }


def _fully_loaded_board_mock() -> MagicMock:
    return _mock_board(
        D5=MagicMock(),
        D9=MagicMock(),
        D11=MagicMock(),
        D12=MagicMock(),
        I2S_BIT_CLOCK=MagicMock(),
        I2S_WORD_SELECT=MagicMock(),
        I2S_DATA=MagicMock(),
    )


def test_build_hardware_fully_loaded_config_builds_accelerometer_and_haptic_output() -> None:
    """A prop declaring every optional section — including accelerometer and
    haptics — builds an accelerometer and a Drv2605EffectOutput alongside its
    other outputs."""
    from hardware.circuitpython.audio_output import AudioEffectOutput
    from hardware.circuitpython.drv2605_output import Drv2605EffectOutput
    from hardware.circuitpython.is31fl3741_output import IS31FL3741EffectOutput
    from hardware.circuitpython.neopixel_output import NeoPixelEffectOutput

    config = parse_device_config(_fully_loaded_config_mapping())
    board_mock = _fully_loaded_board_mock()
    mock_accelerometer = MagicMock()

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_matrix_is31fl3741",
                return_value=MagicMock(),
            )
        )
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_accelerometer",
                return_value=mock_accelerometer,
            )
        )
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_drv2605",
                return_value=MagicMock(),
            )
        )
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_ir",
                return_value=({}, MagicMock(), "pio"),
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

    assert hw.accelerometer is mock_accelerometer
    assert any(isinstance(o, Drv2605EffectOutput) for o in hw.outputs)
    assert any(isinstance(o, IS31FL3741EffectOutput) for o in hw.outputs)
    assert any(isinstance(o, NeoPixelEffectOutput) for o in hw.outputs)
    assert any(isinstance(o, AudioEffectOutput) for o in hw.outputs)
    assert hw.ir_receiver is not None


def test_build_hardware_accelerometer_and_haptics_less_config_omits_both() -> None:
    """The accelerometer/haptics-less counterpart to the fully-loaded prop
    above: every other section stays declared, but omitting accelerometer
    and haptics yields hw.accelerometer is None and no haptic output,
    without either being probed."""
    from hardware.circuitpython.audio_output import AudioEffectOutput
    from hardware.circuitpython.drv2605_output import Drv2605EffectOutput
    from hardware.circuitpython.is31fl3741_output import IS31FL3741EffectOutput
    from hardware.circuitpython.neopixel_output import NeoPixelEffectOutput

    mapping = _fully_loaded_config_mapping()
    del mapping["accelerometer"]
    del mapping["haptics"]
    config = parse_device_config(mapping)
    board_mock = _fully_loaded_board_mock()

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        mock_setup_accelerometer = stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_accelerometer")
        )
        mock_setup_drv2605 = stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_drv2605")
        )
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_matrix_is31fl3741",
                return_value=MagicMock(),
            )
        )
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_ir",
                return_value=({}, MagicMock(), "pio"),
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

    mock_setup_accelerometer.assert_not_called()
    mock_setup_drv2605.assert_not_called()
    assert hw.accelerometer is None
    assert not any(isinstance(o, Drv2605EffectOutput) for o in hw.outputs)
    assert any(isinstance(o, IS31FL3741EffectOutput) for o in hw.outputs)
    assert any(isinstance(o, NeoPixelEffectOutput) for o in hw.outputs)
    assert any(isinstance(o, AudioEffectOutput) for o in hw.outputs)
    assert hw.ir_receiver is not None


# ---------------------------------------------------------------------------
# _describe_ir -- ir line's rx/emitter detail formatting, independent of a
# full build (#763)
# ---------------------------------------------------------------------------


def test_describe_ir_single_rx_pin_names_it_without_multi_receiver_wording() -> None:
    from hardware.circuitpython.device_builder import _describe_ir

    description = _describe_ir(["D11"], {LINE: "D12"})

    assert description == "rx=[D11] emitters=line:D12"


def test_describe_ir_two_rx_pins_names_them_as_ir_multi_receiver() -> None:
    from hardware.circuitpython.device_builder import _describe_ir

    description = _describe_ir(["D11", "D13"], {LINE: "D12"})

    assert description == "rx=[D11 D13] (IR multi-receiver) emitters=line:D12"


def test_describe_ir_lists_every_wired_emitter_in_ir_emitters_order() -> None:
    from hardware.circuitpython.device_builder import _describe_ir

    # Insertion order deliberately reversed from IR_EMITTERS (line, cone,
    # area_of_effect) to confirm the description follows the canonical
    # order, not emitter_pins' own key order -- matching _setup_ir's own
    # wiring order.
    description = _describe_ir(["D11"], {AREA_OF_EFFECT: "D14", CONE: "D13", LINE: "D12"})

    assert description == "rx=[D11] emitters=line:D12 cone:D13 area_of_effect:D14"


def test_describe_ir_no_emitters_notes_none() -> None:
    from hardware.circuitpython.device_builder import _describe_ir

    description = _describe_ir(["D11"], {})

    assert description == "rx=[D11] emitters=(none)"


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
        _patch_neopixel(stack)
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_ir",
                return_value=({}, mock_receiver, "pio"),
            )
        )

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    assert hw.ir_receiver is not None


def test_build_hardware_disabled_ir_section_leaves_ir_receiver_none() -> None:
    """``ir: {enabled: false}`` is neither built nor probed (#692)."""
    config = _neopixel_config_with_ir()
    config.ir.enabled = False
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock(), D11=MagicMock(), D12=MagicMock())

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        _patch_neopixel(stack)
        mock_setup_ir = stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_ir")
        )

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    assert hw.ir_receiver is None
    mock_setup_ir.assert_not_called()


def test_build_hardware_cone_only_ir_config_wires_only_cone_transmitter() -> None:
    """A config declaring only ir.cone (no ir.line/ir.area_of_effect) wires a
    transmitter under CONE and nothing under LINE/AREA_OF_EFFECT.

    Runs the real _setup_ir (only pulseio is stubbed) so this exercises
    build_hardware's config-key-to-emitter mapping end to end — the mapping
    that previously had no direct test (#720)."""
    mapping = {
        "pixels": [{"type": "neopixel", "scopes": {"personal": {"pin": "D5", "count": 10}}}],
        "buttons": ["D9"],
        "ir": {"rx": "D11", "cone": "D13"},
    }
    config = parse_device_config(mapping)
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock(), D11=MagicMock(), D13=MagicMock())

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        _patch_neopixel(stack)
        stack.enter_context(patch.dict(sys.modules, {"pulseio": MagicMock()}))

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    wired_emitters = set(hw.transmit_pump.poll_transmits().keys())
    assert wired_emitters == {CONE}


# ---------------------------------------------------------------------------
# _setup_ir wires one IrTransmitGate into the receiver and every transmitter
# ---------------------------------------------------------------------------


def _wired_gate(receiver_or_transmitter: object) -> object:
    """Return the private ``_gate`` wired onto a receiver or transmitter.

    Isolated helper for the one test below that must observe internal
    wiring directly — there is no public API for "which gate instance is
    this object using", and the test exists specifically to pin that
    internal contract (see AGENTS.md's no-internal-state-access exception).
    """
    return receiver_or_transmitter._gate


def test_setup_ir_injects_same_gate_into_receiver_and_every_transmitter() -> None:
    from hardware.shared.ir_transport import IrTransmitGate

    with ExitStack() as stack:
        stack.enter_context(patch.dict(sys.modules, {"pulseio": MagicMock()}))

        from hardware.circuitpython.device_builder import _setup_ir

        transmitters, receiver, _writer_kind = _setup_ir(
            rx_pins=[MagicMock()],
            emitter_pins={LINE: MagicMock(), CONE: MagicMock(), AREA_OF_EFFECT: MagicMock()},
        )

    receiver_gate = _wired_gate(receiver)
    assert isinstance(receiver_gate, IrTransmitGate)
    for transmitter in transmitters.values():
        assert _wired_gate(transmitter) is receiver_gate


# ---------------------------------------------------------------------------
# _setup_ir chooses the receiver class by resolved rx pin count (#672)
# ---------------------------------------------------------------------------


def _wired_decoder(receiver: object) -> object:
    """Return the private ``_decoder`` wired onto a single receiver.

    See :func:`_wired_gate` above — no public API exposes which decoder
    instance a receiver holds, and the tests below exist specifically to pin
    that internal contract.
    """
    return receiver._decoder


def _wired_decoders(receiver: object) -> list:
    """Return the private ``_decoders`` list wired onto a multi-receiver.

    See :func:`_wired_decoder`.
    """
    return receiver._decoders


def _wired_readers(receiver: object) -> list:
    """Return the private ``_readers`` list wired onto a multi-receiver.

    See :func:`_wired_decoder`.
    """
    return receiver._readers


def test_setup_ir_single_rx_pin_builds_single_receiver_wired_with_passed_decoder() -> None:
    from hardware.shared.ir_transport import InfraredSingleReceiver

    decoder = MagicMock()

    with ExitStack() as stack:
        stack.enter_context(patch.dict(sys.modules, {"pulseio": MagicMock()}))

        from hardware.circuitpython.device_builder import _setup_ir

        _, receiver, _writer_kind = _setup_ir(
            rx_pins=[MagicMock()], emitter_pins={}, decoder=decoder
        )

    assert isinstance(receiver, InfraredSingleReceiver)
    assert _wired_decoder(receiver) is decoder


def test_setup_ir_multiple_rx_pins_builds_multi_receiver_with_one_reader_per_pin() -> None:
    from hardware.circuitpython.infrared_io import PulseInReader
    from hardware.shared.ir_transport import InfraredMultiReceiver

    with ExitStack() as stack:
        stack.enter_context(patch.dict(sys.modules, {"pulseio": MagicMock()}))

        from hardware.circuitpython.device_builder import _setup_ir

        _, receiver, _writer_kind = _setup_ir(
            rx_pins=[MagicMock(), MagicMock(), MagicMock()], emitter_pins={}
        )

    assert isinstance(receiver, InfraredMultiReceiver)
    readers = _wired_readers(receiver)
    assert len(readers) == 3
    assert all(isinstance(reader, PulseInReader) for reader in readers)


def test_setup_ir_multiple_rx_pins_gives_each_reader_a_fresh_decoder_of_the_same_class() -> None:
    from hardware.shared.ir_protocol import AuraInfraredDecoder

    decoder = AuraInfraredDecoder()

    with ExitStack() as stack:
        stack.enter_context(patch.dict(sys.modules, {"pulseio": MagicMock()}))

        from hardware.circuitpython.device_builder import _setup_ir

        _, receiver, _writer_kind = _setup_ir(
            rx_pins=[MagicMock(), MagicMock()], emitter_pins={}, decoder=decoder
        )

    decoders = _wired_decoders(receiver)
    assert len(decoders) == 2
    for wired_decoder in decoders:
        assert type(wired_decoder) is type(decoder)
        assert wired_decoder is not decoder


def test_build_hardware_multi_pin_ir_rx_unknown_pin_raises_same_error_as_any_other_pin() -> None:
    mapping = {"buttons": ["D9"], "ir": {"rx": ["D11", "NOPE"]}}
    config = parse_device_config(mapping)
    board_mock = MagicMock(spec=["D9", "D11"])  # NOPE deliberately absent

    with ExitStack() as stack:
        _enter_hw_patches(stack)

        from hardware.circuitpython.device_builder import build_hardware

        with pytest.raises(ValueError, match=r"ir\.rx\[1\].*NOPE"):
            build_hardware(config, board_module=board_mock)


def test_build_hardware_single_pin_ir_rx_unknown_pin_raises_unindexed_error() -> None:
    mapping = {"buttons": ["D9"], "ir": {"rx": "NOPE"}}
    config = parse_device_config(mapping)
    board_mock = MagicMock(spec=["D9"])  # NOPE deliberately absent

    with ExitStack() as stack:
        _enter_hw_patches(stack)

        from hardware.circuitpython.device_builder import build_hardware

        with pytest.raises(ValueError, match=r"ir\.rx(?!\[).*NOPE"):
            build_hardware(config, board_module=board_mock)


def test_build_hardware_unknown_ir_emitter_pin_name_raises_value_error() -> None:
    mapping = {"buttons": ["D9"], "ir": {"rx": "D11", "line": "NOPE"}}
    config = parse_device_config(mapping)
    board_mock = MagicMock(spec=["D9", "D11"])  # NOPE deliberately absent

    with ExitStack() as stack:
        _enter_hw_patches(stack)

        from hardware.circuitpython.device_builder import build_hardware

        with pytest.raises(ValueError, match=r"ir\.line.*NOPE"):
            build_hardware(config, board_module=board_mock)


def test_build_hardware_neither_accelerometer_nor_haptics_probed_when_undeclared() -> None:
    """Presence-probing is gone (#691): even with an I2C bus available, an
    undeclared accelerometer/haptics section is never probed — absence is
    expressed by omitting the section, not a probe failure."""
    from hardware.circuitpython.drv2605_output import Drv2605EffectOutput

    config = _neopixel_config()
    board_mock = _mock_board(D5=MagicMock(), D6=MagicMock(), D9=MagicMock())
    available_i2c = MagicMock(name="available_i2c")

    with ExitStack() as stack:
        stack.enter_context(patch("hardware.circuitpython.device_builder._setup_external_power"))
        stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_i2c", return_value=available_i2c)
        )
        mock_setup_accelerometer = stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_accelerometer")
        )
        mock_setup_drv2605 = stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_drv2605")
        )
        stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_buttons", return_value=MagicMock())
        )
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    mock_setup_accelerometer.assert_not_called()
    mock_setup_drv2605.assert_not_called()
    assert hw.accelerometer is None
    assert not any(isinstance(o, Drv2605EffectOutput) for o in hw.outputs)


def test_device_hardware_does_not_expose_the_ir_transmit_gate() -> None:
    from hardware.shared.device_hardware import DeviceHardware

    assert "gate" not in DeviceHardware.__slots__
    assert not hasattr(DeviceHardware, "ir_transmit_gate")


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


# ---------------------------------------------------------------------------
# _describe_buttons -- pairs each button label with its declared pin name
# ---------------------------------------------------------------------------


def test_describe_buttons_pairs_each_label_with_its_declared_pin_in_order() -> None:
    from hardware.circuitpython.device_builder import _describe_buttons

    assert _describe_buttons(["GP2", "GP3", "GP4"]) == "A=GP2 B=GP3 C=GP4"


def test_describe_buttons_returns_empty_string_for_no_buttons_declared() -> None:
    from hardware.circuitpython.device_builder import _describe_buttons

    assert _describe_buttons([]) == ""


# ---------------------------------------------------------------------------
# build_hardware — logger spine: banner, external power, i2c, spi, buttons,
# and the closing summary line (#758)
# ---------------------------------------------------------------------------


def test_build_hardware_minimal_config_narrates_exactly_the_unconditional_steps() -> None:
    """A config with no optional sections logs exactly six lines: the opening
    banner, external power, i2c, spi, buttons, and the closing summary --
    nothing else, since pixels/accelerometer/audio/haptics/radio/ir are all
    absent and out of scope for narration in this ticket."""
    config = _minimal_config()
    board_mock = _mock_board(D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    lines = "".join(fragments).splitlines(keepends=True)
    assert len(lines) == 6
    assert lines[0] == "[hw] begin board=unknown-board\n"
    assert lines[1] == "[hw] external_power ok\n"
    assert lines[2] == "[hw] i2c default ok\n"
    assert lines[3] == "[hw] spi default ok\n"
    assert lines[4] == "[hw] buttons A=D9 ok\n"
    assert re.fullmatch(r"\[hw\] ready outputs=0 buttons=1 elapsed_s=\d+\.\d{3}\n", lines[5])


def test_build_hardware_without_logger_injected_produces_no_output_at_all() -> None:
    config = _minimal_config()
    board_mock = _mock_board(D9=MagicMock())
    captured = io.StringIO()

    with ExitStack() as stack:
        _enter_hw_patches(stack)

        from hardware.circuitpython.device_builder import build_hardware

        with redirect_stdout(captured):
            build_hardware(config, board_module=board_mock)

    assert captured.getvalue() == ""


def test_build_hardware_logs_each_button_label_and_pin() -> None:
    config = parse_device_config({"buttons": ["GP2", "GP3"]})
    board_mock = _mock_board(GP2=MagicMock(), GP3=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "[hw] buttons A=GP2 B=GP3 ok\n" in "".join(fragments)


def test_build_hardware_unknown_button_pin_marks_buttons_line_failed_not_prior_line() -> None:
    """The begin-before-_resolve_pin reorder (#758) means an unknown button
    pin name attributes its failure to the still-open buttons line, not to
    whichever line closed just before it -- proving the earlier bug (raising
    before begin() ever opened the line) is fixed."""
    config = parse_device_config({"buttons": ["NOPE"]})
    board_mock = MagicMock(spec=[])  # no attributes -> AttributeError on resolve
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)

        from hardware.circuitpython.device_builder import build_hardware

        with pytest.raises(ValueError, match="NOPE"):
            build_hardware(config, board_module=board_mock, logger=logger)

    lines = "".join(fragments).splitlines(keepends=True)
    assert lines[-2] == "[hw] spi default ok\n"
    assert lines[-1] == "[hw] buttons A=NOPE FAILED\n"


def test_build_hardware_summary_counts_reflect_actually_built_outputs_and_buttons() -> None:
    """The summary line's outputs=/buttons= counts are read off build_hardware's
    own local state (the outputs list and resolved button pins), not off
    logging state -- this ties the counts to a config building two NeoPixel
    outputs and one button, independent of the log lines that led there."""
    config = _neopixel_config()
    board_mock = _mock_board(D5=MagicMock(), D6=MagicMock(), D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    summary = "".join(fragments).splitlines()[-1]
    assert summary.startswith("[hw] ready outputs=2 buttons=1 elapsed_s=")


# ---------------------------------------------------------------------------
# build_hardware — accelerometer and haptics narration (#760)
# ---------------------------------------------------------------------------


def test_build_hardware_logs_accelerometer_ok_line_when_enabled_and_built() -> None:
    config = _neopixel_config_with_accelerometer()
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "[hw] accelerometer lis3dh ok\n" in "".join(fragments)


def test_build_hardware_logs_accelerometer_disabled_line_when_section_disabled() -> None:
    config = _neopixel_config_with_accelerometer()
    config.accelerometer.enabled = False
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "[hw] accelerometer lis3dh disabled\n" in "".join(fragments)


def test_build_hardware_logs_no_accelerometer_line_when_section_absent() -> None:
    config = _minimal_config()
    board_mock = _mock_board(D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "accelerometer" not in "".join(fragments)


def test_build_hardware_accelerometer_no_i2c_bus_marks_its_own_line_failed_and_propagates() -> None:
    """A declared-and-enabled accelerometer with no I2C bus available raises via
    _require_i2c -- the failure must close the accelerometer's own open line,
    not whichever line closed just before it (mirrors the buttons/i2c FAILED
    tests for the #758 spine)."""
    config = _neopixel_config_with_accelerometer()
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        stack.enter_context(patch("hardware.circuitpython.device_builder._setup_external_power"))
        stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_i2c", return_value=None)
        )
        stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_buttons", return_value=MagicMock())
        )
        stack.enter_context(patch("hardware.circuitpython.device_builder._setup_accelerometer"))
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        with pytest.raises(RuntimeError, match="accelerometer"):
            build_hardware(config, board_module=board_mock, logger=logger)

    lines = "".join(fragments).splitlines(keepends=True)
    assert lines[-1] == "[hw] accelerometer lis3dh FAILED\n"


def test_build_hardware_logs_haptics_ok_line_when_enabled_and_built() -> None:
    config = _neopixel_config_with_haptics()
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "[hw] haptics drv2605 ok\n" in "".join(fragments)


def test_build_hardware_logs_haptics_disabled_line_when_section_disabled() -> None:
    config = _neopixel_config_with_haptics()
    config.haptics.enabled = False
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "[hw] haptics drv2605 disabled\n" in "".join(fragments)


def test_build_hardware_logs_no_haptics_line_when_section_absent() -> None:
    config = _minimal_config()
    board_mock = _mock_board(D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "haptics" not in "".join(fragments)


def test_build_hardware_haptics_no_i2c_bus_marks_its_own_line_failed_and_propagates() -> None:
    """A declared-and-enabled haptics section with no I2C bus available raises
    via _require_i2c -- the failure must close the haptics line itself, not
    whichever line closed just before it."""
    config = _neopixel_config_with_haptics()
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        stack.enter_context(patch("hardware.circuitpython.device_builder._setup_external_power"))
        stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_i2c", return_value=None)
        )
        stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_buttons", return_value=MagicMock())
        )
        stack.enter_context(patch("hardware.circuitpython.device_builder._setup_drv2605"))
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        with pytest.raises(RuntimeError, match="haptics"):
            build_hardware(config, board_module=board_mock, logger=logger)

    lines = "".join(fragments).splitlines(keepends=True)
    assert lines[-1] == "[hw] haptics drv2605 FAILED\n"


# ---------------------------------------------------------------------------
# build_hardware — audio narration: inline scalar detail, config-gated (#761)
# ---------------------------------------------------------------------------


def test_build_hardware_audio_config_narrates_voices_max_volume_clips_and_i2s_pins() -> None:
    """An enabled, present audio config opens via logger.begin() carrying
    voice count, max_volume, registered clip count, and the raw I2S pin
    names -- all inline, no _describe_* helper needed for a handful of
    scalars -- and closes with the default ok suffix."""
    from hardware.circuitpython.audio_output import AudioEffectOutput

    config = _neopixel_config_with_audio()
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())
    board_mock.I2S_BIT_CLOCK = MagicMock()
    board_mock.I2S_WORD_SELECT = MagicMock()
    board_mock.I2S_DATA = MagicMock()
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        _patch_neopixel(stack)
        stack.enter_context(
            patch(
                "hardware.circuitpython.audio_output.AudioEffectOutput",
                return_value=MagicMock(spec=AudioEffectOutput),
            )
        )

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert (
        "[hw] audio voices=1 max_volume=0.50 clips=1 i2s_bit_clock=I2S_BIT_CLOCK "
        "i2s_word_select=I2S_WORD_SELECT i2s_data=I2S_DATA ok\n"
    ) in "".join(fragments)


def test_build_hardware_logs_audio_disabled_line_when_section_disabled() -> None:
    """``audio: {enabled: false}`` logs its own disabled line -- not silence."""
    config = _neopixel_config_with_audio()
    config.audio.enabled = False
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "[hw] audio disabled\n" in "".join(fragments)


def test_build_hardware_absent_audio_section_produces_no_audio_line() -> None:
    config = _minimal_config()
    board_mock = _mock_board(D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "audio" not in "".join(fragments)


def test_build_hardware_unknown_i2s_pin_marks_audio_line_failed_not_neighboring_line() -> None:
    """The begin-before-pin-resolution ordering means an unknown I2S pin name
    attributes FAILED to the audio line itself, not the buttons line that
    closed just before it (mirrors #758's buttons case and #759's pixels
    case)."""
    config = _neopixel_config_with_audio(i2s_bit_clock="NOPE")
    board_mock = MagicMock(spec=["D5", "D9"])
    board_mock.D5 = MagicMock()
    board_mock.D9 = MagicMock()
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        with pytest.raises(ValueError, match="NOPE"):
            build_hardware(config, board_module=board_mock, logger=logger)

    lines = "".join(fragments).splitlines(keepends=True)
    assert lines[-2] == "[hw] buttons A=D9 ok\n"
    assert lines[-1] == (
        "[hw] audio voices=1 max_volume=0.50 clips=1 i2s_bit_clock=NOPE "
        "i2s_word_select=I2S_WORD_SELECT i2s_data=I2S_DATA FAILED\n"
    )


# ---------------------------------------------------------------------------
# build_hardware — radio narration (#762)
# ---------------------------------------------------------------------------


def test_build_hardware_logs_radio_ok_line_when_enabled_and_built() -> None:
    config = _neopixel_config_with_radio()
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack, patch_radio=False)
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_radio",
                return_value=MagicMock(),
            )
        )
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "[hw] radio frequency=915.0 node=1 cs=D24 reset=D25 ok\n" in "".join(fragments)


def test_build_hardware_logs_radio_disabled_line_when_section_disabled() -> None:
    config = _neopixel_config_with_radio()
    config.radio.enabled = False
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "[hw] radio frequency=915.0 node=1 cs=D24 reset=D25 disabled\n" in "".join(fragments)


def test_build_hardware_logs_no_radio_line_when_section_absent() -> None:
    config = _minimal_config()
    board_mock = _mock_board(D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "radio" not in "".join(fragments)


def test_build_hardware_radio_no_spi_bus_marks_its_own_line_failed_and_propagates() -> None:
    """A declared-and-enabled radio section with no SPI bus available raises via
    _require_spi -- the failure must close the radio's own open line, leaving
    the earlier spi line's own outcome (whatever it already logged) untouched
    (mirrors the accelerometer/haptics no-I2C-bus FAILED tests)."""
    config = _neopixel_config_with_radio()
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack, patch_radio=False)
        stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_spi", return_value=None)
        )
        mock_setup_radio = stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_radio")
        )
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        with pytest.raises(RuntimeError, match="radio"):
            build_hardware(config, board_module=board_mock, logger=logger)

    mock_setup_radio.assert_not_called()
    text = "".join(fragments)
    lines = text.splitlines(keepends=True)
    assert "[hw] spi sck=SCK mosi=MOSI miso=MISO ok\n" in text
    assert lines[-1] == "[hw] radio frequency=915.0 node=1 cs=D24 reset=D25 FAILED\n"


def test_build_hardware_radio_with_disabled_spi_marks_radio_line_failed() -> None:
    """When the spi section itself is disabled, its line already reads
    "disabled" -- an enabled radio section on top of that still raises via
    _require_spi and closes its own line with FAILED, leaving the earlier spi
    "disabled" line untouched."""
    mapping = {
        "pixels": [{"type": "neopixel", "scopes": {"personal": {"pin": "D5", "count": 10}}}],
        "buttons": ["D9"],
        "spi": {"sck": "SCK", "mosi": "MOSI", "miso": "MISO", "enabled": False},
        "radio": {"cs": "D24", "reset": "D25", "frequency": 915.0, "node": 1},
    }
    config = parse_device_config(mapping)
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack, patch_radio=False)
        mock_setup_radio = stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_radio")
        )
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        with pytest.raises(RuntimeError, match="radio"):
            build_hardware(config, board_module=board_mock, logger=logger)

    mock_setup_radio.assert_not_called()
    text = "".join(fragments)
    lines = text.splitlines(keepends=True)
    assert "[hw] spi disabled\n" in text
    assert lines[-1] == "[hw] radio frequency=915.0 node=1 cs=D24 reset=D25 FAILED\n"


def test_build_hardware_unknown_radio_cs_pin_marks_its_own_line_failed() -> None:
    """The begin-before-pin-resolution ordering means an unknown radio ``cs``
    pin name attributes FAILED to the radio line itself -- _resolve_pin runs
    inside _setup_radio, reached only after logger.begin() has already opened
    the line with the raw, unresolved cs/reset strings (mirrors #758's
    buttons case and #759's pixels case)."""
    mapping = {
        "pixels": [{"type": "neopixel", "scopes": {"personal": {"pin": "D5", "count": 10}}}],
        "buttons": ["D9"],
        "spi": {"sck": "SCK", "mosi": "MOSI", "miso": "MISO"},
        "radio": {"cs": "NOPE", "reset": "D25", "frequency": 915.0, "node": 1},
    }
    config = parse_device_config(mapping)
    board_mock = MagicMock(spec=["D5", "D9", "SCK", "MOSI", "MISO"])
    board_mock.D5 = MagicMock()
    board_mock.D9 = MagicMock()
    board_mock.SCK = MagicMock()
    board_mock.MOSI = MagicMock()
    board_mock.MISO = MagicMock()
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack, patch_radio=False)
        _patch_neopixel(stack)
        # _setup_radio wraps each resolved pin as digitalio.DigitalInOut(...) --
        # the callee is evaluated before _resolve_pin's argument, so digitalio
        # needs a real-shaped DigitalInOut for the unknown-pin ValueError
        # (raised while evaluating that argument) to surface at all, mirroring
        # test_setup_radio_wraps_resolved_pins_into_digitalinout_and_delegates_to_transport.
        stack.enter_context(patch("hardware.circuitpython.device_builder.digitalio"))

        from hardware.circuitpython.device_builder import build_hardware

        with pytest.raises(ValueError, match="NOPE"):
            build_hardware(config, board_module=board_mock, logger=logger)

    lines = "".join(fragments).splitlines(keepends=True)
    assert lines[-1] == "[hw] radio frequency=915.0 node=1 cs=NOPE reset=D25 FAILED\n"


# ---------------------------------------------------------------------------
# build_hardware — ir narration (#763)
# ---------------------------------------------------------------------------


def test_build_hardware_logs_ir_ok_line_naming_rx_emitters_and_writer_kind() -> None:
    config = _neopixel_config_with_ir()
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock(), D11=MagicMock(), D12=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        _patch_neopixel(stack)
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_ir",
                return_value=({LINE: MagicMock()}, MagicMock(), "pio"),
            )
        )

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "[hw] ir rx=[D11] emitters=line:D12 writer=pio ok\n" in "".join(fragments)


def test_build_hardware_logs_ir_writer_kind_matches_what_setup_ir_selected() -> None:
    """The narrated writer= value is exactly what _setup_ir's return surfaced
    -- not re-derived by build_hardware -- so swapping what _setup_ir reports
    (standing in for a writer_factory swap, per #763's own writer_kind
    hand-off tested directly in test_setup_ir.py) changes the logged kind."""
    config = _neopixel_config_with_ir()
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock(), D11=MagicMock(), D12=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        _patch_neopixel(stack)
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_ir",
                return_value=({LINE: MagicMock()}, MagicMock(), "pulseio"),
            )
        )

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "[hw] ir rx=[D11] emitters=line:D12 writer=pulseio ok\n" in "".join(fragments)


def test_build_hardware_logs_ir_multi_receiver_wording_for_two_rx_pins() -> None:
    mapping = {
        "pixels": [{"type": "neopixel", "scopes": {"personal": {"pin": "D5", "count": 10}}}],
        "buttons": ["D9"],
        "ir": {"rx": ["D11", "D13"], "line": "D12"},
    }
    config = parse_device_config(mapping)
    board_mock = _mock_board(
        D5=MagicMock(), D9=MagicMock(), D11=MagicMock(), D12=MagicMock(), D13=MagicMock()
    )
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        _patch_neopixel(stack)
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_ir",
                return_value=({LINE: MagicMock()}, MagicMock(), "pio"),
            )
        )

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "[hw] ir rx=[D11 D13] (IR multi-receiver) emitters=line:D12 writer=pio ok\n" in "".join(
        fragments
    )


def test_build_hardware_logs_ir_disabled_line_when_section_disabled() -> None:
    config = _neopixel_config_with_ir()
    config.ir.enabled = False
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock(), D11=MagicMock(), D12=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        _patch_neopixel(stack)
        mock_setup_ir = stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_ir")
        )

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    mock_setup_ir.assert_not_called()
    assert "[hw] ir rx=[D11] emitters=line:D12 disabled\n" in "".join(fragments)


def test_build_hardware_logs_no_ir_line_when_section_absent() -> None:
    config = _minimal_config()
    board_mock = _mock_board(D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "ir" not in "".join(fragments)


def test_build_hardware_unknown_ir_rx_pin_marks_its_own_line_failed_not_prior_line() -> None:
    """The begin-before-pin-resolution ordering means an unknown ir rx pin name
    attributes FAILED to the ir line itself, leaving the earlier buttons line's
    own ok outcome untouched (mirrors #758's buttons case and #762's radio
    case)."""
    mapping = {
        "pixels": [{"type": "neopixel", "scopes": {"personal": {"pin": "D5", "count": 10}}}],
        "buttons": ["D9"],
        "ir": {"rx": "NOPE", "line": "D12"},
    }
    config = parse_device_config(mapping)
    # spec= so an unlisted attribute (NOPE) raises AttributeError, like a real
    # board module -- a bare MagicMock would fabricate one instead.
    board_mock = MagicMock(spec=["D5", "D9", "D12"])
    board_mock.D5 = MagicMock()
    board_mock.D9 = MagicMock()
    board_mock.D12 = MagicMock()
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        with pytest.raises(ValueError, match="NOPE"):
            build_hardware(config, board_module=board_mock, logger=logger)

    text = "".join(fragments)
    lines = text.splitlines(keepends=True)
    assert "[hw] buttons A=D9 ok\n" in text
    assert lines[-1] == "[hw] ir rx=[NOPE] emitters=line:D12 FAILED\n"


def test_build_hardware_unknown_ir_emitter_pin_marks_its_own_line_failed() -> None:
    """Same begin-before-pin-resolution attribution, for an unknown emitter
    pin name -- _resolve_pin for ir.line raises after the ir line is already
    open with the raw rx=... emitters=... detail."""
    mapping = {
        "pixels": [{"type": "neopixel", "scopes": {"personal": {"pin": "D5", "count": 10}}}],
        "buttons": ["D9"],
        "ir": {"rx": "D11", "line": "NOPE"},
    }
    config = parse_device_config(mapping)
    # spec= so an unlisted attribute (NOPE) raises AttributeError, like a real
    # board module -- a bare MagicMock would fabricate one instead.
    board_mock = MagicMock(spec=["D5", "D9", "D11"])
    board_mock.D5 = MagicMock()
    board_mock.D9 = MagicMock()
    board_mock.D11 = MagicMock()
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        with pytest.raises(ValueError, match="NOPE"):
            build_hardware(config, board_module=board_mock, logger=logger)

    lines = "".join(fragments).splitlines(keepends=True)
    assert lines[-1] == "[hw] ir rx=[D11] emitters=line:NOPE FAILED\n"


def test_build_hardware_ir_rx_only_config_omits_writer_from_ok_line() -> None:
    """An ir section declaring rx but no emitters wires no transmitter, so
    _setup_ir never selects a writer -- the ok line has nothing to report and
    omits the writer= field entirely rather than printing a stale/fake kind."""
    mapping = {
        "pixels": [{"type": "neopixel", "scopes": {"personal": {"pin": "D5", "count": 10}}}],
        "buttons": ["D9"],
        "ir": {"rx": "D11"},
    }
    config = parse_device_config(mapping)
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock(), D11=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        _patch_neopixel(stack)
        stack.enter_context(patch.dict(sys.modules, {"pulseio": MagicMock()}))

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "[hw] ir rx=[D11] emitters=(none) ok\n" in "".join(fragments)

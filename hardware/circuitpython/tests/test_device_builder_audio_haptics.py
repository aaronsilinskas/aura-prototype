"""Tests for device_builder's audio, accelerometer, and haptics subsystems.

Covers ``_setup_audio`` and the audio/accelerometer/haptics slices of
``build_hardware`` (config-gated wiring, hard-error cases, disabled/undeclared
omission, and fully-loaded vs. accelerometer/haptics-less prop scenarios),
plus their build_hardware narration lines. Split out of test_device_builder.py
(#778, part of #767) to keep that suite from growing unbounded; other
build_hardware coverage stays there. Shared config-shape/logging/patch
helpers come from _hw_patch_mocks.py (#775).
"""

from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest

from hardware.circuitpython.tests._hw_patch_mocks import (
    _enter_hw_patches,
    _minimal_config,
    _mock_board,
    _neopixel_config,
    _patch_neopixel,
    _recording_logger,
)
from hardware.shared.device_config import (
    parse_device_config,
)

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


def test_build_hardware_neither_accelerometer_nor_haptics_probed_when_undeclared() -> None:
    """Presence-probing is gone (#691): even with an I2C bus available, an
    undeclared accelerometer/haptics section is never probed — absence is
    expressed by omitting the section, not a probe failure."""
    from hardware.circuitpython.drv2605_output import Drv2605EffectOutput

    config = _neopixel_config()
    board_mock = _mock_board(D5=MagicMock(), D6=MagicMock(), D9=MagicMock())
    available_i2c = MagicMock(name="available_i2c")

    with ExitStack() as stack:
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

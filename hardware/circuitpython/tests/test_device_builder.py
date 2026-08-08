"""Tests for device_builder.build_hardware — the general logger spine, plus
whatever build_hardware coverage doesn't have a more specific subsystem home.

Verifies build_hardware's unconditional narration (opening banner, buttons,
and closing summary lines) and button-pin-resolution failure attribution
through its injected logger (#758), the ``_describe_buttons`` line-formatting
helper, and that ``transmit_pump``/``network_controls`` are the same
HardwareNetworkControls instance (#608). Matrix (IS31FL3741) and NeoPixel
pixel-branch coverage (_setup_matrix_is31fl3741, _setup_neopixels,
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
their narration) live in test_device_builder_radio_ir.py (#779); this file
still uses a neopixel-plus-audio-plus-haptics config as a vehicle for one
piece of non-pixel/non-bus/non-audio-haptics/non-radio/non-ir coverage that
spans pixels, audio, and haptics (pixels outputs preceding audio/haptic
outputs). All hardware modules (board, busio, pulseio, digitalio) are patched
so this suite runs under CPython.
"""

from __future__ import annotations

import io
import re
from contextlib import ExitStack, redirect_stdout
from unittest.mock import MagicMock, patch

import pytest

from engine.log import Logger
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

"""Tests for device_builder.build_hardware — the core, cross-subsystem tests
that don't belong to any one subsystem cluster: output ordering across
multiple components, that ``transmit_pump``/``network_controls`` are the
same HardwareNetworkControls instance (#608), the
``_construct_with_optional_address`` helper shared by the accelerometer,
magnetometer, and haptics ``_setup_*`` functions (#843), and the
``_address_suffix`` helper those same three sections' descriptions (plus the
matrix pixel entry's) format their address override through (#852).

Also hosts the two comprehensive full-sequence narration tests -- one
all-enabled config, one all-disabled config -- that are the verbatim lock for
every ``[hw]`` line family in one place (#852): the happy-path "ok" vocabulary
and the "disabled"/"held off" vocabulary, each asserted as the complete
ordered line list for its config. Per-subsystem test_device_builder_*.py
files keep one representative narrated line per component plus the outcome
variants neither comprehensive config reaches (i2c's "no bus", ir's
writer=pio/writer=pulseio, and IR multi-receiver); the begin/end/fail
contract itself is covered directly by hardware/shared/tests/
test_build_narration.py, not repeated here. Per-subsystem coverage (pixels,
buses/power, audio/haptics, radio/ir, buttons/logging) lives in the sibling
test_device_builder_*.py files split out under #767; shared config/patch
helpers come from _hw_patch_mocks.py.
"""

from __future__ import annotations

import re
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from hardware.circuitpython.tests._hw_patch_mocks import (
    _enter_hw_patches,
    _mock_board,
    _neopixel_config,
    _patch_neopixel,
    _recording_logger,
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
# _address_suffix — the shared I2C address-override formatter every bare I2C
# device's boot-log description forwards through: the matrix pixel entry and
# the accelerometer/magnetometer/haptics sections (#852)
# ---------------------------------------------------------------------------


def test_address_suffix_omits_the_field_entirely_when_address_is_none() -> None:
    from hardware.circuitpython.device_builder import _address_suffix

    assert _address_suffix(None) == ""


def test_address_suffix_formats_a_configured_override_as_two_digit_hex() -> None:
    from hardware.circuitpython.device_builder import _address_suffix

    assert _address_suffix(0x19) == " address=0x19"


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


# ---------------------------------------------------------------------------
# build_hardware — two comprehensive full-sequence narration tests: the
# verbatim lock for every [hw] line family in one place (#852), replacing the
# per-subsystem exact-log-string coverage the split test_device_builder_*.py
# files previously carried one outcome at a time. One config enables every
# gated section; the other declares every gated section but disables it --
# together they pin the entire "ok" vocabulary and the entire
# "disabled"/"held off" vocabulary. Per-subsystem files keep one
# representative narrated line per component plus the outcome variants
# neither config here can reach (i2c's "no bus", ir's writer=pio/
# writer=pulseio, and IR multi-receiver).
# ---------------------------------------------------------------------------


def _all_enabled_hardware_config_mapping() -> dict:
    """Return a raw mapping declaring every gated build_hardware section, enabled."""
    return {
        "high_current_rail": {"pin": "GP28", "active_high": True},
        "i2c": {"sda": "GP4", "scl": "GP5"},
        "spi": {"sck": "SCK", "mosi": "MOSI", "miso": "MISO"},
        "pixels": [
            {"type": "matrix", "cols": 13, "scope_rows": {"global.main": [0, 5]}},
            {"type": "neopixel", "scopes": {"personal": {"pin": "D5", "count": 10}}},
        ],
        "buttons": ["D9"],
        "accelerometer": {},
        "magnetometer": {},
        "audio": {
            "voices": 1,
            "max_volume": 0.5,
            "i2s_bit_clock": "I2S_BIT_CLOCK",
            "i2s_word_select": "I2S_WORD_SELECT",
            "i2s_data": "I2S_DATA",
        },
        "haptics": {},
        "radio": {"cs": "D24", "reset": "D25", "frequency": 915.0, "node": 1},
        "sdcard": {"cs": "D26", "mount": "/sd"},
        "ir": {"rx": "D11", "line": "D12"},
    }


def _all_enabled_hardware_board_mock() -> MagicMock:
    return _mock_board(
        GP28=MagicMock(),
        D5=MagicMock(),
        D9=MagicMock(),
        D24=MagicMock(),
        D25=MagicMock(),
        D26=MagicMock(),
        D11=MagicMock(),
        D12=MagicMock(),
        I2S_BIT_CLOCK=MagicMock(),
        I2S_WORD_SELECT=MagicMock(),
        I2S_DATA=MagicMock(),
    )


def test_build_hardware_all_enabled_config_narrates_the_complete_ok_line_sequence() -> None:
    """The happy-path verbatim lock: every gated section built and closed 'ok'
    (or its own success suffix), asserted as the complete ordered line list."""
    from hardware.circuitpython.audio_output import AudioEffectOutput

    config = parse_device_config(_all_enabled_hardware_config_mapping())
    board_mock = _all_enabled_hardware_board_mock()
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        stack.enter_context(patch("hardware.circuitpython.device_builder.digitalio"))
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_matrix_is31fl3741",
                return_value=MagicMock(),
            )
        )
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_accelerometer",
                return_value=MagicMock(),
            )
        )
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_magnetometer",
                return_value=MagicMock(),
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
                "hardware.circuitpython.device_builder._setup_radio",
                return_value=MagicMock(),
            )
        )
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_sdcard",
                return_value=MagicMock(),
            )
        )
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_ir",
                return_value=({"line": MagicMock()}, MagicMock(), "pio"),
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

        build_hardware(config, board_module=board_mock, logger=logger)

    lines = "".join(fragments).splitlines(keepends=True)
    assert lines[:-1] == [
        "[hw] begin board=unknown-board\n",
        "[hw] high_current_rail pin=GP28 active_high=True asserted\n",
        "[hw] i2c scl=GP5 sda=GP4 ok\n",
        "[hw] spi sck=SCK mosi=MOSI miso=MISO ok\n",
        "[hw] pixels[0] matrix cols=13 scope_rows=[global.main:0-5] brightness=1.00 ok\n",
        "[hw] pixels[1] neopixel pin=D5 count=10 order=GRB scope=personal ok\n",
        "[hw] buttons A=D9 ok\n",
        "[hw] accelerometer lis3dh ok\n",
        "[hw] magnetometer mmc5603 ok\n",
        "[hw] audio voices=1 max_volume=0.50 i2s_bit_clock=I2S_BIT_CLOCK "
        "i2s_word_select=I2S_WORD_SELECT i2s_data=I2S_DATA ok\n",
        "[hw] haptics drv2605 ok\n",
        "[hw] radio frequency=915.0 node=1 cs=D24 reset=D25 ok\n",
        "[hw] sdcard mount=/sd cs=D26 ok\n",
        "[hw] ir rx=[D11] emitters=line:D12 writer=pio ok\n",
    ]
    assert re.fullmatch(r"\[hw\] ready outputs=4 buttons=1 elapsed_s=\d+\.\d{3}\n", lines[-1])


def _all_disabled_hardware_config_mapping() -> dict:
    """Return a raw mapping declaring every gated build_hardware section, all
    disabled -- the ``enabled: false`` counterpart to
    _all_enabled_hardware_config_mapping. high_current_rail is the one
    section that still builds despite ``enabled: false`` (its pin still
    drives, deasserted), so its outcome reads "held off" rather than
    "disabled"."""
    return {
        "high_current_rail": {"pin": "GP28", "active_high": True, "enabled": False},
        "i2c": {"sda": "GP4", "scl": "GP5", "enabled": False},
        "spi": {"sck": "SCK", "mosi": "MOSI", "miso": "MISO", "enabled": False},
        "pixels": [
            {
                "type": "matrix",
                "cols": 13,
                "scope_rows": {"global.main": [0, 5]},
                "enabled": False,
            },
            {
                "type": "neopixel",
                "scopes": {"personal": {"pin": "D5", "count": 10}},
                "enabled": False,
            },
        ],
        "buttons": ["D9"],
        "accelerometer": {"enabled": False},
        "magnetometer": {"enabled": False},
        "audio": {
            "voices": 1,
            "max_volume": 0.5,
            "i2s_bit_clock": "I2S_BIT_CLOCK",
            "i2s_word_select": "I2S_WORD_SELECT",
            "i2s_data": "I2S_DATA",
            "enabled": False,
        },
        "haptics": {"enabled": False},
        "radio": {
            "cs": "D24",
            "reset": "D25",
            "frequency": 915.0,
            "node": 1,
            "enabled": False,
        },
        "sdcard": {"cs": "D26", "mount": "/sd", "enabled": False},
        "ir": {"rx": "D11", "line": "D12", "enabled": False},
    }


def test_build_hardware_all_disabled_config_narrates_the_complete_disabled_line_sequence() -> None:
    """The disabled-vocabulary verbatim lock: every gated section declared but
    disabled, asserted as the complete ordered line list. None of these
    sections' setup helpers need patching -- narrate_skip means build_hardware
    never calls them at all when a section is disabled."""
    config = parse_device_config(_all_disabled_hardware_config_mapping())
    board_mock = _mock_board(GP28=MagicMock(), D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        stack.enter_context(patch("hardware.circuitpython.device_builder.digitalio"))

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    lines = "".join(fragments).splitlines(keepends=True)
    assert lines[:-1] == [
        "[hw] begin board=unknown-board\n",
        "[hw] high_current_rail pin=GP28 active_high=True held off\n",
        "[hw] i2c disabled\n",
        "[hw] spi disabled\n",
        "[hw] pixels[0] matrix disabled\n",
        "[hw] pixels[1] neopixel disabled\n",
        "[hw] buttons A=D9 ok\n",
        "[hw] accelerometer lis3dh disabled\n",
        "[hw] magnetometer mmc5603 disabled\n",
        "[hw] audio disabled\n",
        "[hw] haptics drv2605 disabled\n",
        "[hw] radio frequency=915.0 node=1 cs=D24 reset=D25 disabled\n",
        "[hw] sdcard mount=/sd cs=D26 disabled\n",
        "[hw] ir rx=[D11] emitters=line:D12 disabled\n",
    ]
    assert re.fullmatch(r"\[hw\] ready outputs=0 buttons=1 elapsed_s=\d+\.\d{3}\n", lines[-1])

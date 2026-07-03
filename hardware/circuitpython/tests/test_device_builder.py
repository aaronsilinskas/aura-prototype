"""Tests for device_builder.build_hardware — matrix, NeoPixel, audio, motor, and IR branches.

Verifies that build_hardware produces the correct EffectOutput for each
pixels.type (matrix and neopixel) and that audio, DRV2605 motor, IR, and
I2C bus injection paths wire up correctly.  All hardware modules (board,
busio, pulseio, digitalio) are patched so this suite runs under CPython.
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


def _enter_hw_patches(stack: ExitStack, own_i2c: object | None = None) -> MagicMock:
    """Enter patches for all CircuitPython hardware setup helpers.

    Returns the patched ``_setup_i2c`` mock so callers can assert on it (e.g.
    whether it was invoked at all). *own_i2c* is the bus it returns when
    build_hardware constructs one itself.
    """
    stack.enter_context(patch("hardware.circuitpython.device_builder._setup_external_power"))
    mock_setup_i2c = stack.enter_context(
        patch(
            "hardware.circuitpython.device_builder._setup_i2c",
            return_value=own_i2c if own_i2c is not None else MagicMock(),
        )
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
    return mock_setup_i2c


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
# build_hardware produces NeoPixelEffectOutput for scope_pixels strip config
# ---------------------------------------------------------------------------


def _segmented_strip_config():
    """Return a DeviceConfig with one neopixel strip entry using scope_pixels."""
    mapping = {
        "pixels": [
            {
                "type": "neopixel",
                "pin": "D5",
                "count": 20,
                "scope_pixels": {
                    "personal": [0, 10],
                    "ambient": [10, 20],
                },
            }
        ],
        "buttons": ["D9"],
    }
    return parse_device_config(mapping)


def test_build_hardware_segmented_strip_produces_one_output() -> None:
    from hardware.circuitpython.neopixel_output import NeoPixelEffectOutput

    config = _segmented_strip_config()
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        mock_neopixel = stack.enter_context(patch("hardware.circuitpython.device_builder.neopixel"))
        mock_neopixel.NeoPixel.return_value = MagicMock()

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    pixel_outputs = [o for o in hw.outputs if isinstance(o, NeoPixelEffectOutput)]
    assert len(pixel_outputs) == 1


def test_build_hardware_segmented_strip_output_serves_all_segment_scopes() -> None:
    from hardware.circuitpython.neopixel_output import NeoPixelEffectOutput

    config = _segmented_strip_config()
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        mock_neopixel = stack.enter_context(patch("hardware.circuitpython.device_builder.neopixel"))
        mock_neopixel.NeoPixel.return_value = MagicMock()

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    pixel_output = next(o for o in hw.outputs if isinstance(o, NeoPixelEffectOutput))
    all_keys = {sv.keys[0] for sv in pixel_output.scopes}
    assert all_keys == {"personal", "ambient"}


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


# ---------------------------------------------------------------------------
# build_hardware's I2C bus: caller-supplied vs. self-constructed
# ---------------------------------------------------------------------------


def test_build_hardware_uses_caller_supplied_i2c_bus_for_matrix() -> None:
    config = _matrix_config()
    board_mock = _mock_board(D9=MagicMock(), D10=MagicMock())
    supplied_i2c = MagicMock(name="caller_i2c")

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        mock_setup_matrix = stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_matrix_is31fl3741",
                return_value=MagicMock(),
            )
        )

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, i2c=supplied_i2c)

    mock_setup_matrix.assert_called_once_with(supplied_i2c)


def test_build_hardware_does_not_construct_its_own_bus_when_i2c_supplied() -> None:
    config = _matrix_config()
    board_mock = _mock_board(D9=MagicMock(), D10=MagicMock())
    supplied_i2c = MagicMock(name="caller_i2c")

    with ExitStack() as stack:
        mock_setup_i2c = _enter_hw_patches(stack)
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_matrix_is31fl3741",
                return_value=MagicMock(),
            )
        )

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, i2c=supplied_i2c)

    mock_setup_i2c.assert_not_called()


def test_build_hardware_constructs_its_own_bus_when_i2c_omitted() -> None:
    config = _matrix_config()
    board_mock = _mock_board(D9=MagicMock(), D10=MagicMock())

    with ExitStack() as stack:
        mock_setup_i2c = _enter_hw_patches(stack)
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_matrix_is31fl3741",
                return_value=MagicMock(),
            )
        )

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock)

    mock_setup_i2c.assert_called_once()


def test_build_hardware_uses_its_own_constructed_bus_for_matrix_when_i2c_omitted() -> None:
    config = _matrix_config()
    board_mock = _mock_board(D9=MagicMock(), D10=MagicMock())
    own_i2c = MagicMock(name="own_i2c")

    with ExitStack() as stack:
        _enter_hw_patches(stack, own_i2c=own_i2c)
        mock_setup_matrix = stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_matrix_is31fl3741",
                return_value=MagicMock(),
            )
        )

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock)

    mock_setup_matrix.assert_called_once_with(own_i2c)


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
        stack.enter_context(patch("hardware.circuitpython.device_builder.pulseio"))

        from hardware.circuitpython.device_builder import _setup_ir

        transmitters, receiver = _setup_ir(
            rx_pin=MagicMock(),
            line_pin=MagicMock(),
            cone_pin=MagicMock(),
            aoe_pin=MagicMock(),
        )

    receiver_gate = _wired_gate(receiver)
    assert isinstance(receiver_gate, IrTransmitGate)
    for transmitter in transmitters.values():
        assert _wired_gate(transmitter) is receiver_gate


# ---------------------------------------------------------------------------
# _setup_external_power only drives the rail on boards that have one
# ---------------------------------------------------------------------------


class _BoardWithoutExternalPower:
    """A board stub with no EXTERNAL_POWER attribute, unlike MagicMock which
    would fabricate one on access."""


def test_setup_external_power_enables_rail_when_board_has_pin() -> None:
    board_mock = _mock_board(EXTERNAL_POWER=MagicMock())

    with ExitStack() as stack:
        stack.enter_context(patch("hardware.circuitpython.device_builder.board", board_mock))
        mock_digitalio = stack.enter_context(
            patch("hardware.circuitpython.device_builder.digitalio")
        )

        from hardware.circuitpython.device_builder import _setup_external_power

        _setup_external_power()

    mock_digitalio.DigitalInOut.assert_called_once_with(board_mock.EXTERNAL_POWER)
    mock_digitalio.DigitalInOut.return_value.switch_to_output.assert_called_once_with(value=True)


def test_setup_external_power_is_noop_when_board_has_no_pin() -> None:
    with ExitStack() as stack:
        stack.enter_context(
            patch("hardware.circuitpython.device_builder.board", _BoardWithoutExternalPower())
        )
        mock_digitalio = stack.enter_context(
            patch("hardware.circuitpython.device_builder.digitalio")
        )

        from hardware.circuitpython.device_builder import _setup_external_power

        _setup_external_power()

    mock_digitalio.DigitalInOut.assert_not_called()


# ---------------------------------------------------------------------------
# _setup_i2c / build_hardware handle a board with no I2C devices wired
# ---------------------------------------------------------------------------


def test_setup_i2c_returns_none_when_no_pullup_found() -> None:
    with ExitStack() as stack:
        mock_busio = stack.enter_context(patch("hardware.circuitpython.device_builder.busio"))
        mock_busio.I2C.side_effect = RuntimeError(
            "No pull up found on SDA or SCL; check your wiring"
        )
        stack.enter_context(patch("hardware.circuitpython.device_builder.board", _mock_board()))

        from hardware.circuitpython.device_builder import _setup_i2c

        assert _setup_i2c() is None


def test_build_hardware_omits_accelerometer_and_motor_when_i2c_unavailable() -> None:
    config = _neopixel_config()
    board_mock = _mock_board(D5=MagicMock(), D6=MagicMock(), D9=MagicMock())

    with ExitStack() as stack:
        stack.enter_context(patch("hardware.circuitpython.device_builder._setup_external_power"))
        stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_i2c", return_value=None)
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
        mock_neopixel = stack.enter_context(patch("hardware.circuitpython.device_builder.neopixel"))
        mock_neopixel.NeoPixel.return_value = MagicMock()

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    mock_setup_accelerometer.assert_not_called()
    mock_setup_drv2605.assert_not_called()
    assert hw.accelerometer is None


def test_build_hardware_matrix_config_raises_when_i2c_unavailable() -> None:
    """Matrix pixels are config-gated (declared, expected present) rather than
    presence-probed like the accelerometer/motor — a missing I2C bus is a real
    wiring fault, so this fails loud instead of silently skipping the matrix."""
    config = _matrix_config()
    board_mock = _mock_board(D9=MagicMock(), D10=MagicMock())

    with ExitStack() as stack:
        stack.enter_context(patch("hardware.circuitpython.device_builder._setup_external_power"))
        stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_i2c", return_value=None)
        )
        mock_setup_matrix = stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_matrix_is31fl3741")
        )
        stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_buttons", return_value=MagicMock())
        )

        from hardware.circuitpython.device_builder import build_hardware

        with pytest.raises(RuntimeError, match="matrix"):
            build_hardware(config, board_module=board_mock)

    mock_setup_matrix.assert_not_called()


def test_device_hardware_does_not_expose_the_ir_transmit_gate() -> None:
    from hardware.circuitpython.device_builder import DeviceHardware

    assert "gate" not in DeviceHardware.__slots__
    assert not hasattr(DeviceHardware, "ir_transmit_gate")

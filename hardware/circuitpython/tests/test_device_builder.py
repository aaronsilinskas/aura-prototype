"""Tests for device_builder.build_hardware — matrix, NeoPixel, audio, haptic, and IR branches.

Verifies that build_hardware produces the correct EffectOutput for each
pixels.type (matrix and neopixel) and that audio, DRV2605 haptic driver, IR,
and I2C bus injection paths wire up correctly. Also covers open_config_i2c,
the public bus entry point onto _setup_i2c reachable without a full
build_hardware call. All hardware modules (board, busio, pulseio, digitalio)
are patched so this suite runs under CPython.
"""

from __future__ import annotations

import io
import re
import sys
from contextlib import ExitStack, redirect_stdout
from typing import NamedTuple
from unittest.mock import MagicMock, patch

import pytest

from engine.log import Logger
from engine.network import AREA_OF_EFFECT, CONE, LINE
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


def _mixed_matrix_and_neopixel_config():
    """Return a DeviceConfig whose pixels list has a matrix entry then a neopixel entry.

    A device driving both a matrix and NeoPixel strips in one ``config.pixels``
    list is a real, common configuration (see #613).
    """
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
            },
            {"type": "neopixel", "scopes": {"personal": {"pin": "D5", "count": 10}}},
        ],
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


# ---------------------------------------------------------------------------
# build_hardware produces IS31FL3741EffectOutput for matrix config
# ---------------------------------------------------------------------------


def test_build_hardware_matrix_only_config_includes_matrix_output_in_bundle() -> None:
    """build_hardware's pixels wiring is a single delegating call to
    _setup_pixels — matrix-branch details (resolution, buffer scopes, driver
    identity, brightness forwarding) are covered directly on _setup_pixels and
    _setup_matrix_is31fl3741; this only confirms the output reaches the bundle.
    """
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

    assert sum(isinstance(o, IS31FL3741EffectOutput) for o in hw.outputs) == 1


def test_setup_matrix_is31fl3741_drives_scaling_from_brightness() -> None:
    """_setup_matrix_is31fl3741 sets LED scaling to round(brightness * 0xFF) and
    leaves global_current pinned at 0xFF."""
    with ExitStack() as stack:
        mock_matrix_cls = stack.enter_context(
            patch("adafruit_is31fl3741.adafruit_rgbmatrixqt.Adafruit_RGBMatrixQT")
        )
        driver = MagicMock()
        mock_matrix_cls.return_value = driver

        from hardware.circuitpython.device_builder import _setup_matrix_is31fl3741

        result = _setup_matrix_is31fl3741(MagicMock(), 0.2)

    assert result is driver
    # 0.2 * 0xFF == 0x33 -- the old hard-coded calibration byte.
    driver.set_led_scaling.assert_called_once_with(0x33)
    assert driver.global_current == 0xFF


def test_setup_matrix_is31fl3741_full_brightness_drives_max_scaling() -> None:
    """Brightness 1.0 drives the full 0xFF scaling byte (stock full-brightness boot)."""
    with ExitStack() as stack:
        mock_matrix_cls = stack.enter_context(
            patch("adafruit_is31fl3741.adafruit_rgbmatrixqt.Adafruit_RGBMatrixQT")
        )
        driver = MagicMock()
        mock_matrix_cls.return_value = driver

        from hardware.circuitpython.device_builder import _setup_matrix_is31fl3741

        _setup_matrix_is31fl3741(MagicMock(), 1.0)

    driver.set_led_scaling.assert_called_once_with(0xFF)


def test_setup_matrix_is31fl3741_returns_driver_after_transient_failures() -> None:
    """A matrix that only responds on a later attempt still returns the driver
    once construction succeeds, within the retry window."""
    with ExitStack() as stack:
        mock_matrix_cls = stack.enter_context(
            patch("adafruit_is31fl3741.adafruit_rgbmatrixqt.Adafruit_RGBMatrixQT")
        )
        driver = MagicMock()
        mock_matrix_cls.side_effect = [Exception("not ready"), Exception("not ready"), driver]
        stack.enter_context(patch("hardware.circuitpython.device_builder.time.sleep"))

        from hardware.circuitpython.device_builder import _setup_matrix_is31fl3741

        result = _setup_matrix_is31fl3741(MagicMock(), 1.0)

    assert result is driver


def test_setup_matrix_is31fl3741_raises_runtime_error_past_deadline() -> None:
    """A matrix that never responds raises RuntimeError naming the peripheral
    and the timeout, instead of hanging forever."""
    with ExitStack() as stack:
        mock_matrix_cls = stack.enter_context(
            patch("adafruit_is31fl3741.adafruit_rgbmatrixqt.Adafruit_RGBMatrixQT")
        )
        mock_matrix_cls.side_effect = Exception("not ready")
        stack.enter_context(patch("hardware.circuitpython.device_builder.time.sleep"))
        # monotonic values: one initial read for the deadline, then one read at
        # the first retry check -- already past the 3s window.
        stack.enter_context(
            patch("hardware.circuitpython.device_builder.time.monotonic", side_effect=[0, 4])
        )

        from hardware.circuitpython.device_builder import _setup_matrix_is31fl3741

        with pytest.raises(RuntimeError, match="IS31FL3741 matrix did not respond within 3s"):
            _setup_matrix_is31fl3741(MagicMock(), 1.0)


# ---------------------------------------------------------------------------
# _setup_neopixels — construct NeoPixel strips and legacy per-scope strips
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


def test_setup_neopixels_produces_one_output_per_legacy_scope() -> None:
    from hardware.circuitpython.neopixel_output import NeoPixelEffectOutput

    pixels_cfg = _neopixel_config().pixels[0]
    board_mock = _mock_board(D5=MagicMock(), D6=MagicMock())

    with ExitStack() as stack:
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import _setup_neopixels

        outputs = _setup_neopixels(pixels_cfg, board_mock)

    pixel_outputs = [o for o in outputs if isinstance(o, NeoPixelEffectOutput)]
    assert len(pixel_outputs) == 2


def test_setup_neopixels_each_legacy_scope_output_declares_its_own_scope() -> None:
    pixels_cfg = _neopixel_config().pixels[0]
    board_mock = _mock_board(D5=MagicMock(), D6=MagicMock())

    with ExitStack() as stack:
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import _setup_neopixels

        outputs = _setup_neopixels(pixels_cfg, board_mock)

    all_scope_keys = {sv.keys[0] for o in outputs for sv in o.scopes}
    assert all_scope_keys == {"personal", "directional"}
    for o in outputs:
        assert len(o.scopes) == 1


def test_setup_neopixels_exposes_shared_strip_for_a_single_scope() -> None:
    """The NeoPixel output's ``strip`` accessor returns the built strip object.

    The pixel profiler builds one max-length strip, then rebuilds sweep wrappers
    around it, reaching it through this public accessor.
    """
    pixels_cfg = _neopixel_config(scopes={"personal": {"pin": "D5", "count": 10}}).pixels[0]
    board_mock = _mock_board(D5=MagicMock())
    strip = MagicMock(name="neopixel_strip")

    with ExitStack() as stack:
        mock_neopixel = MagicMock()
        stack.enter_context(patch.dict(sys.modules, {"neopixel": mock_neopixel}))
        mock_neopixel.NeoPixel.return_value = strip

        from hardware.circuitpython.device_builder import _setup_neopixels

        outputs = _setup_neopixels(pixels_cfg, board_mock)

    assert outputs[0].strip is strip


def test_setup_neopixels_resolves_each_strip_pin_from_board() -> None:
    d5_pin = MagicMock(name="D5")
    d6_pin = MagicMock(name="D6")
    board_mock = _mock_board(D5=d5_pin, D6=d6_pin)
    pixels_cfg = _neopixel_config().pixels[0]

    with ExitStack() as stack:
        mock_neopixel = _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import _setup_neopixels

        _setup_neopixels(pixels_cfg, board_mock)

    called_pins = {c.args[0] for c in mock_neopixel.NeoPixel.call_args_list}
    assert called_pins == {d5_pin, d6_pin}


def test_setup_neopixels_constructs_strip_with_configured_count() -> None:
    pixels_cfg = _neopixel_config(scopes={"personal": {"pin": "D5", "count": 17}}).pixels[0]
    board_mock = _mock_board(D5=MagicMock())

    with ExitStack() as stack:
        mock_neopixel = _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import _setup_neopixels

        _setup_neopixels(pixels_cfg, board_mock)

    assert mock_neopixel.NeoPixel.call_args.args[1] == 17


def test_setup_neopixels_applies_configured_brightness_at_construction() -> None:
    """_setup_neopixels applies each strip's configured brightness to the
    neopixel.NeoPixel object at construction (the library scales at show())."""
    pixels_cfg = _neopixel_config(
        scopes={
            "personal": {"pin": "D5", "count": 10, "brightness": 0.5},
            "directional": {"pin": "D6", "count": 4},
        }
    ).pixels[0]
    board_mock = _mock_board(D5=MagicMock(), D6=MagicMock())

    with ExitStack() as stack:
        mock_neopixel = _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import _setup_neopixels

        _setup_neopixels(pixels_cfg, board_mock)

    brightness_kwargs = {c.kwargs.get("brightness") for c in mock_neopixel.NeoPixel.call_args_list}
    assert brightness_kwargs == {0.5, 1.0}


def test_setup_neopixels_constructs_every_strip_with_auto_write_false() -> None:
    """auto_write=False ensures flush() drives all hardware writes rather than
    every pixel assignment triggering an immediate SPI/UART transaction."""
    pixels_cfg = _neopixel_config().pixels[0]
    board_mock = _mock_board(D5=MagicMock(), D6=MagicMock())

    with ExitStack() as stack:
        mock_neopixel = _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import _setup_neopixels

        _setup_neopixels(pixels_cfg, board_mock)

    for call_kwargs in mock_neopixel.NeoPixel.call_args_list:
        assert call_kwargs.kwargs.get("auto_write") is False, (
            "Each NeoPixel strip must be constructed with auto_write=False"
        )


def test_setup_neopixels_raises_on_unknown_pin() -> None:
    pixels_cfg = _neopixel_config(
        scopes={"personal": {"pin": "NONEXISTENT_PIN", "count": 5}},
    ).pixels[0]
    board_mock = MagicMock(spec=[])  # no attributes → AttributeError on getattr

    with ExitStack() as stack:
        stack.enter_context(patch.dict(sys.modules, {"neopixel": MagicMock()}))

        from hardware.circuitpython.device_builder import _setup_neopixels

        with pytest.raises(ValueError, match="NONEXISTENT_PIN"):
            _setup_neopixels(pixels_cfg, board_mock)


def test_setup_neopixels_produces_one_output_for_a_segmented_strip() -> None:
    from hardware.circuitpython.neopixel_output import NeoPixelEffectOutput

    pixels_cfg = _segmented_strip_config().pixels[0]
    board_mock = _mock_board(D5=MagicMock())

    with ExitStack() as stack:
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import _setup_neopixels

        outputs = _setup_neopixels(pixels_cfg, board_mock)

    pixel_outputs = [o for o in outputs if isinstance(o, NeoPixelEffectOutput)]
    assert len(pixel_outputs) == 1


def test_setup_neopixels_segmented_strip_output_serves_all_segment_scopes() -> None:
    pixels_cfg = _segmented_strip_config().pixels[0]
    board_mock = _mock_board(D5=MagicMock())

    with ExitStack() as stack:
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import _setup_neopixels

        outputs = _setup_neopixels(pixels_cfg, board_mock)

    all_keys = {sv.keys[0] for sv in outputs[0].scopes}
    assert all_keys == {"personal", "ambient"}


# ---------------------------------------------------------------------------
# _setup_pixels — dispatch each pixels config entry to its output branch
# ---------------------------------------------------------------------------


def test_setup_pixels_dispatches_matrix_config_to_matrix_branch() -> None:
    from hardware.circuitpython.is31fl3741_output import IS31FL3741EffectOutput

    config = _matrix_config(brightness=0.2)
    board_mock = _mock_board()
    i2c = MagicMock(name="i2c")
    driver = MagicMock(name="is31fl3741_driver")

    with ExitStack() as stack:
        mock_setup_matrix = stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_matrix_is31fl3741",
                return_value=driver,
            )
        )

        from hardware.circuitpython.device_builder import _setup_pixels

        outputs = _setup_pixels(config.pixels[0], board_mock, i2c)

    assert len(outputs) == 1
    assert isinstance(outputs[0], IS31FL3741EffectOutput)
    assert outputs[0].matrix is driver
    mock_setup_matrix.assert_called_once_with(i2c, 0.2)


def test_setup_pixels_dispatches_neopixel_config_to_neopixel_branch() -> None:
    from hardware.circuitpython.neopixel_output import NeoPixelEffectOutput

    config = _neopixel_config()
    board_mock = _mock_board(D5=MagicMock(), D6=MagicMock())

    with ExitStack() as stack:
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import _setup_pixels

        outputs = _setup_pixels(config.pixels[0], board_mock, i2c=None)

    assert len(outputs) == 2
    assert all(isinstance(o, NeoPixelEffectOutput) for o in outputs)


def test_setup_pixels_matrix_config_with_no_i2c_raises_runtime_error() -> None:
    """Matrix pixels are config-gated (declared, expected present) rather than
    presence-probed like the accelerometer/haptics driver, so a missing I2C
    bus fails loud instead of silently skipping the matrix."""
    config = _matrix_config()
    board_mock = _mock_board()

    with ExitStack() as stack:
        mock_setup_matrix = stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_matrix_is31fl3741")
        )

        from hardware.circuitpython.device_builder import _setup_pixels

        with pytest.raises(RuntimeError, match="matrix"):
            _setup_pixels(config.pixels[0], board_mock, i2c=None)

    mock_setup_matrix.assert_not_called()


def test_setup_pixels_skips_disabled_matrix_entry() -> None:
    """A disabled matrix entry is neither built nor probed -- not even the
    no-I2C-bus check runs, since the entry is skipped outright (#692)."""
    mapping = {
        "pixels": [
            {
                "type": "matrix",
                "cols": 13,
                "scope_rows": {"global.main": [0, 5]},
                "enabled": False,
            }
        ],
        "buttons": ["D9"],
    }
    config = parse_device_config(mapping)
    board_mock = _mock_board()

    with ExitStack() as stack:
        mock_setup_matrix = stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_matrix_is31fl3741")
        )

        from hardware.circuitpython.device_builder import _setup_pixels

        outputs = _setup_pixels(config.pixels[0], board_mock, i2c=None)

    assert outputs == []
    mock_setup_matrix.assert_not_called()


def test_setup_pixels_skips_disabled_neopixel_entry() -> None:
    mapping = {
        "pixels": [
            {
                "type": "neopixel",
                "scopes": {"personal": {"pin": "D5", "count": 10}},
                "enabled": False,
            }
        ],
        "buttons": ["D9"],
    }
    config = parse_device_config(mapping)
    board_mock = _mock_board(D5=MagicMock())

    with ExitStack() as stack:
        mock_neopixel = _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import _setup_pixels

        outputs = _setup_pixels(config.pixels[0], board_mock, i2c=None)

    assert outputs == []
    mock_neopixel.NeoPixel.assert_not_called()


# ---------------------------------------------------------------------------
# _describe_pixel_entry -- pixels[n] narration line formatting, independent
# of a full build (#759)
# ---------------------------------------------------------------------------


def test_describe_pixel_entry_matrix_formats_cols_scope_rows_and_brightness() -> None:
    from hardware.circuitpython.device_builder import _describe_pixel_entry

    config = _matrix_config(brightness=0.5)

    description = _describe_pixel_entry(0, config.pixels[0])

    assert description == (
        "pixels[0] matrix cols=13 "
        "scope_rows=[global.buff:0-1 global.debuff:1-2 global.main:2-5 "
        "personal:5-7 directional:7-8 ambient:8-9] brightness=0.50"
    )


def test_describe_pixel_entry_disabled_matrix_produces_skipped_line_not_detail() -> None:
    from hardware.circuitpython.device_builder import _describe_pixel_entry

    mapping = {
        "pixels": [
            {"type": "matrix", "cols": 13, "scope_rows": {"global.main": [0, 5]}, "enabled": False}
        ],
        "buttons": ["D9"],
    }
    config = parse_device_config(mapping)

    description = _describe_pixel_entry(1, config.pixels[0])

    assert description == "pixels[1] matrix disabled — skipped"


def test_describe_pixel_entry_neopixel_strips_form_formats_pin_count_order_and_segments() -> None:
    from hardware.circuitpython.device_builder import _describe_pixel_entry

    config = _segmented_strip_config()

    description = _describe_pixel_entry(0, config.pixels[0])

    assert description == (
        "pixels[0] neopixel pin=D5 count=20 order=GRB scope_pixels=[personal:0-10 ambient:10-20]"
    )


def test_describe_pixel_entry_neopixel_legacy_scopes_form_names_each_strips_scope_key() -> None:
    from hardware.circuitpython.device_builder import _describe_pixel_entry

    config = _neopixel_config()

    description = _describe_pixel_entry(0, config.pixels[0])

    assert description == (
        "pixels[0] neopixel pin=D5 count=10 order=GRB scope=personal | "
        "pin=D6 count=4 order=GRB scope=directional"
    )


def test_describe_pixel_entry_disabled_neopixel_produces_skipped_line_not_detail() -> None:
    from hardware.circuitpython.device_builder import _describe_pixel_entry

    mapping = {
        "pixels": [
            {
                "type": "neopixel",
                "scopes": {"personal": {"pin": "D5", "count": 10}},
                "enabled": False,
            }
        ],
        "buttons": ["D9"],
    }
    config = parse_device_config(mapping)

    description = _describe_pixel_entry(2, config.pixels[0])

    assert description == "pixels[2] neopixel disabled — skipped"


# ---------------------------------------------------------------------------
# build_hardware's pixels wiring — thin orchestration over _setup_pixels
# ---------------------------------------------------------------------------


def test_build_hardware_neopixel_only_config_includes_all_strip_outputs_in_bundle() -> None:
    """build_hardware's pixels wiring is a single delegating call to
    _setup_pixels — strip-construction details (brightness, auto_write,
    pin resolution, count, segments, unknown-pin failures) are covered
    directly on _setup_neopixels; this only confirms the outputs reach the
    bundle.
    """
    from hardware.circuitpython.neopixel_output import NeoPixelEffectOutput

    config = _neopixel_config()
    board_mock = _mock_board(D5=MagicMock(), D6=MagicMock(), D9=MagicMock())

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    assert sum(isinstance(o, NeoPixelEffectOutput) for o in hw.outputs) == 2


def test_build_hardware_mixed_matrix_and_neopixel_config_produces_outputs_in_config_order() -> None:
    """A device driving both a matrix and NeoPixel strips in one
    config.pixels list dispatches correctly, with outputs following config
    order (#613) — per-entry dispatch itself is covered directly on
    _setup_pixels."""
    from hardware.circuitpython.is31fl3741_output import IS31FL3741EffectOutput
    from hardware.circuitpython.neopixel_output import NeoPixelEffectOutput

    config = _mixed_matrix_and_neopixel_config()
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_matrix_is31fl3741",
                return_value=MagicMock(),
            )
        )
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    pixel_output_types = [
        type(o) for o in hw.outputs if isinstance(o, (IS31FL3741EffectOutput, NeoPixelEffectOutput))
    ]
    assert pixel_output_types == [IS31FL3741EffectOutput, NeoPixelEffectOutput]


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


def _neopixel_config_with_audio():
    """Return a DeviceConfig with a neopixel pixels section and audio config."""
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
                return_value=({}, MagicMock()),
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
                return_value=({}, MagicMock()),
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
                return_value=({}, mock_receiver),
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

    mock_setup_matrix.assert_called_once_with(supplied_i2c, 1.0)


def test_build_hardware_does_not_construct_its_own_bus_when_i2c_supplied() -> None:
    config = _matrix_config()
    board_mock = _mock_board(D9=MagicMock(), D10=MagicMock())
    supplied_i2c = MagicMock(name="caller_i2c")

    with ExitStack() as stack:
        mock_setup_i2c = _enter_hw_patches(stack).i2c
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
        mock_setup_i2c = _enter_hw_patches(stack).i2c
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

    mock_setup_matrix.assert_called_once_with(own_i2c, 1.0)


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

        transmitters, receiver = _setup_ir(
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

        _, receiver = _setup_ir(rx_pins=[MagicMock()], emitter_pins={}, decoder=decoder)

    assert isinstance(receiver, InfraredSingleReceiver)
    assert _wired_decoder(receiver) is decoder


def test_setup_ir_multiple_rx_pins_builds_multi_receiver_with_one_reader_per_pin() -> None:
    from hardware.circuitpython.infrared_io import PulseInReader
    from hardware.shared.ir_transport import InfraredMultiReceiver

    with ExitStack() as stack:
        stack.enter_context(patch.dict(sys.modules, {"pulseio": MagicMock()}))

        from hardware.circuitpython.device_builder import _setup_ir

        _, receiver = _setup_ir(rx_pins=[MagicMock(), MagicMock(), MagicMock()], emitter_pins={})

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

        _, receiver = _setup_ir(
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


def _i2c_config(sda: str = "GP4", scl: str = "GP5"):
    """Return an I2CConfig for testing _setup_i2c's named-pin branch."""
    mapping = {
        "buttons": ["D9"],
        "i2c": {"sda": sda, "scl": scl},
    }
    return parse_device_config(mapping).i2c


def test_setup_i2c_returns_none_when_no_pullup_found() -> None:
    with ExitStack() as stack:
        mock_busio = stack.enter_context(patch("hardware.circuitpython.device_builder.busio"))
        mock_busio.I2C.side_effect = RuntimeError(
            "No pull up found on SDA or SCL; check your wiring"
        )
        board_mock = _mock_board(SCL=MagicMock(), SDA=MagicMock())

        from hardware.circuitpython.device_builder import _setup_i2c

        assert _setup_i2c(None, board_mock) is None


def test_setup_i2c_uses_board_default_pins_when_no_config_present() -> None:
    """Absent an i2c config, _setup_i2c falls back to board.SCL/board.SDA,
    matching pre-#679 behaviour for boards whose ``board`` module already
    aliases the bus pins."""
    board_mock = _mock_board(SCL=MagicMock(name="SCL"), SDA=MagicMock(name="SDA"))

    with ExitStack() as stack:
        mock_busio = stack.enter_context(patch("hardware.circuitpython.device_builder.busio"))
        mock_bus = MagicMock(name="bus")
        mock_busio.I2C.return_value = mock_bus

        from hardware.circuitpython.device_builder import _setup_i2c

        result = _setup_i2c(None, board_mock)

    mock_busio.I2C.assert_called_once_with(board_mock.SCL, board_mock.SDA)
    assert result is mock_bus


def test_setup_i2c_resolves_named_pins_and_constructs_bus_in_scl_sda_order() -> None:
    """With an i2c config present, _setup_i2c resolves sda/scl by name against
    board (for boards lacking SCL/SDA aliases) and preserves busio.I2C's
    existing (scl, sda) positional argument order."""
    scl_pin = MagicMock(name="scl_pin")
    sda_pin = MagicMock(name="sda_pin")
    board_mock = _mock_board(GP5=scl_pin, GP4=sda_pin)
    i2c_config = _i2c_config(sda="GP4", scl="GP5")

    with ExitStack() as stack:
        mock_busio = stack.enter_context(patch("hardware.circuitpython.device_builder.busio"))
        mock_bus = MagicMock(name="bus")
        mock_busio.I2C.return_value = mock_bus

        from hardware.circuitpython.device_builder import _setup_i2c

        result = _setup_i2c(i2c_config, board_mock)

    mock_busio.I2C.assert_called_once_with(scl_pin, sda_pin)
    assert result is mock_bus


def test_setup_i2c_bad_pin_name_raises_value_error() -> None:
    board_mock = MagicMock(spec=["GP5"])  # only scl resolves, sda has no attribute
    board_mock.GP5 = MagicMock(name="GP5")
    i2c_config = _i2c_config(sda="NONEXISTENT_PIN", scl="GP5")

    with ExitStack() as stack:
        stack.enter_context(patch("hardware.circuitpython.device_builder.busio"))

        from hardware.circuitpython.device_builder import _setup_i2c

        with pytest.raises(ValueError, match="NONEXISTENT_PIN"):
            _setup_i2c(i2c_config, board_mock)


def test_setup_i2c_disabled_config_builds_no_bus() -> None:
    """``enabled: false`` on i2c builds no bus at all -- not a fall back to
    the board's default SCL/SDA pins (#692)."""
    board_mock = _mock_board(SCL=MagicMock(), SDA=MagicMock())
    i2c_config = _i2c_config(sda="GP4", scl="GP5")
    i2c_config.enabled = False

    with ExitStack() as stack:
        mock_busio = stack.enter_context(patch("hardware.circuitpython.device_builder.busio"))

        from hardware.circuitpython.device_builder import _setup_i2c

        result = _setup_i2c(i2c_config, board_mock)

    assert result is None
    mock_busio.I2C.assert_not_called()


# ---------------------------------------------------------------------------
# open_config_i2c -- public bus entry point, a thin wrapper over _setup_i2c
# reachable without a full build_hardware call (#725, moved from the
# profiler-output module profiler_report, where it had drifted from
# _setup_i2c: this is _setup_i2c's own behaviour, reached publicly)
# ---------------------------------------------------------------------------


def _device_config_with_i2c(sda: str = "GP4", scl: str = "GP5"):
    """Return a DeviceConfig for testing open_config_i2c's named-pin branch."""
    mapping = {
        "buttons": ["D9"],
        "i2c": {"sda": sda, "scl": scl},
    }
    return parse_device_config(mapping)


def test_open_config_i2c_resolves_named_pins_and_constructs_bus_in_scl_sda_order() -> None:
    scl_pin = MagicMock(name="scl_pin")
    sda_pin = MagicMock(name="sda_pin")
    board_mock = _mock_board(GP5=scl_pin, GP4=sda_pin)
    config = _device_config_with_i2c(sda="GP4", scl="GP5")

    with ExitStack() as stack:
        mock_busio = stack.enter_context(patch("hardware.circuitpython.device_builder.busio"))
        mock_bus = MagicMock(name="bus")
        mock_busio.I2C.return_value = mock_bus

        from hardware.circuitpython.device_builder import open_config_i2c

        result = open_config_i2c(config, board_mock)

    mock_busio.I2C.assert_called_once_with(scl_pin, sda_pin)
    assert result is mock_bus


def test_open_config_i2c_uses_board_default_pins_when_no_config_present() -> None:
    board_mock = _mock_board(SCL=MagicMock(name="SCL"), SDA=MagicMock(name="SDA"))
    config = parse_device_config({"buttons": ["D9"]})

    with ExitStack() as stack:
        mock_busio = stack.enter_context(patch("hardware.circuitpython.device_builder.busio"))
        mock_bus = MagicMock(name="bus")
        mock_busio.I2C.return_value = mock_bus

        from hardware.circuitpython.device_builder import open_config_i2c

        result = open_config_i2c(config, board_mock)

    mock_busio.I2C.assert_called_once_with(board_mock.SCL, board_mock.SDA)
    assert result is mock_bus


def test_open_config_i2c_bad_pin_name_raises_field_named_value_error() -> None:
    board_mock = MagicMock(spec=["GP5"])  # only scl resolves, sda has no attribute
    board_mock.GP5 = MagicMock(name="GP5")
    config = _device_config_with_i2c(sda="NONEXISTENT_PIN", scl="GP5")

    with ExitStack() as stack:
        stack.enter_context(patch("hardware.circuitpython.device_builder.busio"))

        from hardware.circuitpython.device_builder import open_config_i2c

        with pytest.raises(ValueError, match=r"i2c\.sda.*NONEXISTENT_PIN"):
            open_config_i2c(config, board_mock)


def test_open_config_i2c_disabled_section_builds_no_bus() -> None:
    """``enabled: false`` on i2c builds no bus at all, honoured the same way
    _setup_i2c honours it -- not a fall back to the board's default pins."""
    config = _device_config_with_i2c()
    config.i2c.enabled = False
    board_mock = _mock_board(SCL=MagicMock(), SDA=MagicMock())

    with ExitStack() as stack:
        mock_busio = stack.enter_context(patch("hardware.circuitpython.device_builder.busio"))

        from hardware.circuitpython.device_builder import open_config_i2c

        result = open_config_i2c(config, board_mock)

    assert result is None
    mock_busio.I2C.assert_not_called()


def test_open_config_i2c_returns_none_when_no_pullup_found() -> None:
    """A RuntimeError from busio.I2C (no pull-up wired) is caught and
    reported as None, not propagated -- open_config_i2c honours this the
    same way _setup_i2c does."""
    config = parse_device_config({"buttons": ["D9"]})
    board_mock = _mock_board(SCL=MagicMock(), SDA=MagicMock())

    with ExitStack() as stack:
        mock_busio = stack.enter_context(patch("hardware.circuitpython.device_builder.busio"))
        mock_busio.I2C.side_effect = RuntimeError(
            "No pull up found on SDA or SCL; check your wiring"
        )

        from hardware.circuitpython.device_builder import open_config_i2c

        assert open_config_i2c(config, board_mock) is None


def test_open_config_i2c_never_returns_a_never_reset_stemma_bus() -> None:
    """The returned bus must be a fresh busio.I2C -- CircuitPython tears it
    down on reload -- never board.STEMMA_I2C(), which holds never_reset and
    would leave the I2C peripheral claimed for the next program on the same
    pins. This is the one behavioural fact the old profiler_report
    docstring recorded that the #725 merge into _setup_i2c had to preserve."""
    config = _device_config_with_i2c()
    board_mock = _mock_board(GP4=MagicMock(), GP5=MagicMock())
    board_mock.STEMMA_I2C = MagicMock(side_effect=AssertionError("must not call STEMMA_I2C"))

    with ExitStack() as stack:
        mock_busio = stack.enter_context(patch("hardware.circuitpython.device_builder.busio"))
        mock_bus = MagicMock(name="bus")
        mock_busio.I2C.return_value = mock_bus

        from hardware.circuitpython.device_builder import open_config_i2c

        result = open_config_i2c(config, board_mock)

    board_mock.STEMMA_I2C.assert_not_called()
    mock_busio.I2C.assert_called_once()
    assert result is mock_bus


# ---------------------------------------------------------------------------
# _setup_spi -- the shared SPI bus radio (and future SPI peripherals) reach
# through, mirroring _setup_i2c's configured-pins-or-board-default shape
# ---------------------------------------------------------------------------


def _spi_config(sck: str = "GP2", mosi: str = "GP3", miso: str = "GP4"):
    """Return an SPIConfig for testing _setup_spi's named-pin branch."""
    mapping = {
        "buttons": ["D9"],
        "spi": {"sck": sck, "mosi": mosi, "miso": miso},
    }
    return parse_device_config(mapping).spi


def test_setup_spi_uses_board_default_bus_when_no_config_present() -> None:
    """Absent an spi config, _setup_spi falls back to board.SPI() -- mirrors
    _setup_i2c's board.SCL/board.SDA fallback."""
    board_mock = _mock_board()
    own_bus = MagicMock(name="board_spi_bus")
    board_mock.SPI.return_value = own_bus

    from hardware.circuitpython.device_builder import _setup_spi

    result = _setup_spi(None, board_mock)

    board_mock.SPI.assert_called_once_with()
    assert result is own_bus


def test_setup_spi_resolves_named_pins_and_constructs_bus_in_sck_mosi_miso_order() -> None:
    """With an spi config present, _setup_spi resolves sck/mosi/miso by name
    against board and constructs busio.SPI from them, instead of falling
    back to board.SPI()."""
    sck_pin = MagicMock(name="sck_pin")
    mosi_pin = MagicMock(name="mosi_pin")
    miso_pin = MagicMock(name="miso_pin")
    board_mock = _mock_board(GP2=sck_pin, GP3=mosi_pin, GP4=miso_pin)
    spi_config = _spi_config(sck="GP2", mosi="GP3", miso="GP4")

    with ExitStack() as stack:
        mock_busio = stack.enter_context(patch("hardware.circuitpython.device_builder.busio"))
        mock_bus = MagicMock(name="bus")
        mock_busio.SPI.return_value = mock_bus

        from hardware.circuitpython.device_builder import _setup_spi

        result = _setup_spi(spi_config, board_mock)

    mock_busio.SPI.assert_called_once_with(sck_pin, MOSI=mosi_pin, MISO=miso_pin)
    assert result is mock_bus


def test_setup_spi_bad_pin_name_raises_value_error() -> None:
    board_mock = MagicMock(spec=["GP2", "GP3"])  # miso has no attribute
    spi_config = _spi_config(sck="GP2", mosi="GP3", miso="NONEXISTENT_PIN")

    with ExitStack() as stack:
        stack.enter_context(patch("hardware.circuitpython.device_builder.busio"))

        from hardware.circuitpython.device_builder import _setup_spi

        with pytest.raises(ValueError, match="NONEXISTENT_PIN"):
            _setup_spi(spi_config, board_mock)


def test_setup_spi_disabled_config_builds_no_bus() -> None:
    """``enabled: false`` on spi builds no bus at all -- not a fall back to
    board.SPI(), mirroring _setup_i2c's disabled behaviour."""
    board_mock = _mock_board()
    spi_config = _spi_config()
    spi_config.enabled = False

    with ExitStack() as stack:
        mock_busio = stack.enter_context(patch("hardware.circuitpython.device_builder.busio"))

        from hardware.circuitpython.device_builder import _setup_spi

        result = _setup_spi(spi_config, board_mock)

    assert result is None
    mock_busio.SPI.assert_not_called()
    board_mock.SPI.assert_not_called()


def test_build_hardware_passes_i2c_config_and_board_to_setup_i2c() -> None:
    """build_hardware threads config.i2c and the board module into the
    self-constructed-bus branch, so a bad-alias board with an i2c section
    resolves named pins rather than falling back to board.SCL/board.SDA."""
    mapping = {
        "buttons": ["D9"],
        "i2c": {"sda": "GP4", "scl": "GP5"},
    }
    config = parse_device_config(mapping)
    board_mock = _mock_board(D9=MagicMock())

    with ExitStack() as stack:
        mock_setup_i2c = _enter_hw_patches(stack).i2c

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock)

    mock_setup_i2c.assert_called_once_with(config.i2c, board_mock)


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
# _setup_external_power -- return value drives build_hardware's ok/no-rail line
# ---------------------------------------------------------------------------


def test_setup_external_power_returns_true_when_board_has_pin() -> None:
    board_mock = _mock_board(EXTERNAL_POWER=MagicMock())

    with ExitStack() as stack:
        stack.enter_context(patch("hardware.circuitpython.device_builder.board", board_mock))
        stack.enter_context(patch("hardware.circuitpython.device_builder.digitalio"))

        from hardware.circuitpython.device_builder import _setup_external_power

        assert _setup_external_power() is True


def test_setup_external_power_returns_false_when_board_has_no_pin() -> None:
    with ExitStack() as stack:
        stack.enter_context(
            patch("hardware.circuitpython.device_builder.board", _BoardWithoutExternalPower())
        )
        stack.enter_context(patch("hardware.circuitpython.device_builder.digitalio"))

        from hardware.circuitpython.device_builder import _setup_external_power

        assert _setup_external_power() is False


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


def test_build_hardware_logs_no_rail_when_board_has_no_external_power() -> None:
    config = _minimal_config()
    board_mock = _mock_board(D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_external_power",
                return_value=False,
            )
        )
        stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_i2c", return_value=MagicMock())
        )
        stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_spi", return_value=MagicMock())
        )
        stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_buttons", return_value=MagicMock())
        )

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "[hw] external_power no rail\n" in "".join(fragments)


def test_build_hardware_logs_configured_i2c_pins() -> None:
    config = parse_device_config({"buttons": ["D9"], "i2c": {"sda": "GP4", "scl": "GP5"}})
    board_mock = _mock_board(D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "[hw] i2c scl=GP5 sda=GP4 ok\n" in "".join(fragments)


def test_build_hardware_logs_i2c_disabled_line_when_section_explicitly_disabled() -> None:
    config = parse_device_config(
        {"buttons": ["D9"], "i2c": {"sda": "GP4", "scl": "GP5", "enabled": False}}
    )
    board_mock = _mock_board(D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "[hw] i2c disabled\n" in "".join(fragments)


def test_build_hardware_logs_i2c_no_bus_outcome_when_no_pullup_found() -> None:
    """An absent i2c section still builds a real bus on default pins -- when
    that construction finds no pull-up (busio.I2C's RuntimeError, caught
    inside _setup_i2c), the line reports "no bus", distinct from "disabled"."""
    config = _minimal_config()
    board_mock = _mock_board(D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        stack.enter_context(patch("hardware.circuitpython.device_builder._setup_external_power"))
        stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_i2c", return_value=None)
        )
        stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_spi", return_value=MagicMock())
        )
        stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_buttons", return_value=MagicMock())
        )

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "[hw] i2c default no bus\n" in "".join(fragments)


def test_build_hardware_logs_configured_spi_pins() -> None:
    config = parse_device_config(
        {"buttons": ["D9"], "spi": {"sck": "GP2", "mosi": "GP3", "miso": "GP4"}}
    )
    board_mock = _mock_board(D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "[hw] spi sck=GP2 mosi=GP3 miso=GP4 ok\n" in "".join(fragments)


def test_build_hardware_logs_spi_disabled_line_when_section_explicitly_disabled() -> None:
    config = parse_device_config(
        {
            "buttons": ["D9"],
            "spi": {"sck": "GP2", "mosi": "GP3", "miso": "GP4", "enabled": False},
        }
    )
    board_mock = _mock_board(D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "[hw] spi disabled\n" in "".join(fragments)


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


def test_build_hardware_i2c_setup_failure_marks_i2c_line_failed_and_propagates() -> None:
    """A component that raises something other than the RuntimeError
    _setup_i2c itself catches (e.g. a wedged bus) still closes its own line
    with FAILED, and the exception still propagates -- the single
    whole-function try/except (#758), not a per-component one."""
    config = _minimal_config()
    board_mock = _mock_board(D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        stack.enter_context(patch("hardware.circuitpython.device_builder._setup_external_power"))
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_i2c",
                side_effect=OSError("i2c bus wedged"),
            )
        )

        from hardware.circuitpython.device_builder import build_hardware

        with pytest.raises(OSError, match="i2c bus wedged"):
            build_hardware(config, board_module=board_mock, logger=logger)

    lines = "".join(fragments).splitlines(keepends=True)
    assert lines[-2] == "[hw] external_power ok\n"
    assert lines[-1] == "[hw] i2c default FAILED\n"


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
# build_hardware — pixels narration: indexed pixels[n] entries (#759)
# ---------------------------------------------------------------------------


def test_build_hardware_mixed_pixels_config_narrates_indexed_lines_in_config_order() -> None:
    """A config mixing a matrix entry and a NeoPixel entry produces one
    pixels[n] line per entry, indexed and ordered to match config.pixels --
    each carrying its own type-specific detail."""
    config = _mixed_matrix_and_neopixel_config()
    board_mock = _mock_board(D5=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_matrix_is31fl3741",
                return_value=MagicMock(),
            )
        )
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    lines = "".join(fragments).splitlines(keepends=True)
    matrix_line = (
        "[hw] pixels[0] matrix cols=13 "
        "scope_rows=[global.buff:0-1 global.debuff:1-2 global.main:2-5 "
        "personal:5-7 directional:7-8 ambient:8-9] brightness=1.00 ok\n"
    )
    neopixel_line = "[hw] pixels[1] neopixel pin=D5 count=10 order=GRB scope=personal ok\n"
    assert lines.index(matrix_line) < lines.index(neopixel_line)


def test_build_hardware_disabled_pixel_entry_narrates_skipped_line_not_ok() -> None:
    """A disabled pixels entry logs its own skipped line -- not silence, and
    not the normal ok suffix an enabled entry would get."""
    mapping = {
        "pixels": [
            {
                "type": "neopixel",
                "scopes": {"personal": {"pin": "D5", "count": 10}},
                "enabled": False,
            }
        ],
        "buttons": ["D9"],
    }
    config = parse_device_config(mapping)
    board_mock = _mock_board(D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    text = "".join(fragments)
    assert "[hw] pixels[0] neopixel disabled — skipped\n" in text
    assert "pixels[0] neopixel disabled — skipped ok" not in text


def test_build_hardware_empty_pixels_list_produces_no_pixel_lines() -> None:
    config = _minimal_config()
    board_mock = _mock_board(D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "pixels[" not in "".join(fragments)


def test_build_hardware_unknown_neopixel_pin_marks_its_own_pixels_line_failed() -> None:
    """The begin-before-pin-resolution ordering means an unknown NeoPixel pin
    name attributes FAILED to its own pixels[n] line, leaving an earlier,
    already-succeeded entry's line untouched (#759, mirrors #758's buttons
    case)."""
    mapping = {
        "pixels": [
            {"type": "neopixel", "scopes": {"personal": {"pin": "D5", "count": 10}}},
            {"type": "neopixel", "scopes": {"directional": {"pin": "NOPE", "count": 4}}},
        ],
        "buttons": ["D9"],
    }
    config = parse_device_config(mapping)
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
    assert lines[-2] == "[hw] pixels[0] neopixel pin=D5 count=10 order=GRB scope=personal ok\n"
    assert (
        lines[-1] == "[hw] pixels[1] neopixel pin=NOPE count=4 order=GRB scope=directional FAILED\n"
    )


def test_build_hardware_matrix_with_no_i2c_marks_its_own_pixels_line_failed() -> None:
    """A declared, enabled matrix entry still raises RuntimeError when no I2C
    bus is available -- that raise closes the matrix's own pixels[n] line
    with FAILED via the outer try/fail spine (#758), not a prior line."""
    config = _matrix_config()
    board_mock = _mock_board()
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        stack.enter_context(patch("hardware.circuitpython.device_builder._setup_external_power"))
        stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_i2c", return_value=None)
        )
        stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_spi", return_value=MagicMock())
        )
        mock_setup_matrix = stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_matrix_is31fl3741")
        )

        from hardware.circuitpython.device_builder import build_hardware

        with pytest.raises(RuntimeError, match="matrix"):
            build_hardware(config, board_module=board_mock, logger=logger)

    mock_setup_matrix.assert_not_called()
    lines = "".join(fragments).splitlines(keepends=True)
    assert lines[-2] == "[hw] spi default ok\n"
    assert lines[-1] == (
        "[hw] pixels[0] matrix cols=13 "
        "scope_rows=[global.buff:0-1 global.debuff:1-2 global.main:2-5 "
        "personal:5-7 directional:7-8 ambient:8-9] brightness=1.00 FAILED\n"
    )

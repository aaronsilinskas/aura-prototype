"""Tests for device_builder's pixel subsystem -- the matrix (IS31FL3741) and
NeoPixel branches of ``pixels`` config entries.

Covers ``_setup_matrix_is31fl3741``, ``_setup_neopixels``, ``_setup_pixels``,
and ``_describe_pixel_entry`` (the ``pixels[n]`` narration line formatter),
plus the pixel-related slices of ``build_hardware``: output ordering when a
config drives both a matrix and NeoPixel strips in one ``config.pixels``
list (#613), and the ``pixels[n]`` narration lines emitted during a full
build (#759). Split out of test_device_builder.py (#776) to keep that suite
from growing without bound; non-pixel build_hardware coverage stays there.
Config-shape and hardware-patch helpers come from _hw_patch_mocks.py.
"""

from __future__ import annotations

import sys
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest

from hardware.circuitpython.tests._hw_patch_mocks import (
    _enter_hw_patches,
    _matrix_config,
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
# Helpers
# ---------------------------------------------------------------------------


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


def test_setup_matrix_is31fl3741_omits_address_kwarg_when_none() -> None:
    """A ``None`` address means no override -- the driver's own default
    (0x30) applies, so the construction call must not pass ``address=`` at
    all rather than passing ``address=None``."""
    with ExitStack() as stack:
        mock_matrix_cls = stack.enter_context(
            patch("adafruit_is31fl3741.adafruit_rgbmatrixqt.Adafruit_RGBMatrixQT")
        )
        driver = MagicMock()
        mock_matrix_cls.return_value = driver

        from hardware.circuitpython.device_builder import _setup_matrix_is31fl3741

        i2c = MagicMock(name="i2c")
        _setup_matrix_is31fl3741(i2c, 1.0, None)

    _, kwargs = mock_matrix_cls.call_args
    assert "address" not in kwargs


def test_setup_matrix_is31fl3741_passes_configured_address_to_driver() -> None:
    import adafruit_is31fl3741

    with ExitStack() as stack:
        mock_matrix_cls = stack.enter_context(
            patch("adafruit_is31fl3741.adafruit_rgbmatrixqt.Adafruit_RGBMatrixQT")
        )
        driver = MagicMock()
        mock_matrix_cls.return_value = driver

        from hardware.circuitpython.device_builder import _setup_matrix_is31fl3741

        i2c = MagicMock(name="i2c")
        _setup_matrix_is31fl3741(i2c, 1.0, 0x31)

    mock_matrix_cls.assert_called_once_with(
        i2c, address=0x31, allocate=adafruit_is31fl3741.MUST_BUFFER
    )


def test_setup_matrix_is31fl3741_raises_runtime_error_past_deadline() -> None:
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
    mock_setup_matrix.assert_called_once_with(i2c, 0.2, None)


def test_setup_pixels_forwards_configured_address_to_matrix_setup() -> None:
    config = _matrix_config(address=0x31)
    board_mock = _mock_board()
    i2c = MagicMock(name="i2c")

    with ExitStack() as stack:
        mock_setup_matrix = stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_matrix_is31fl3741",
                return_value=MagicMock(),
            )
        )

        from hardware.circuitpython.device_builder import _setup_pixels

        _setup_pixels(config.pixels[0], board_mock, i2c)

    mock_setup_matrix.assert_called_once_with(i2c, 1.0, 0x31)


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


def test_describe_pixel_entry_matrix_with_configured_address_appends_address_suffix() -> None:
    from hardware.circuitpython.device_builder import _describe_pixel_entry

    config = _matrix_config(brightness=0.5, address=0x31)

    description = _describe_pixel_entry(0, config.pixels[0])

    assert description == (
        "pixels[0] matrix cols=13 "
        "scope_rows=[global.buff:0-1 global.debuff:1-2 global.main:2-5 "
        "personal:5-7 directional:7-8 ambient:8-9] brightness=0.50 address=0x31"
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
# _pixel_kind -- "matrix" vs "neopixel" by config type, independent of a full
# build (#852)
# ---------------------------------------------------------------------------


def test_pixel_kind_names_a_matrix_config_matrix() -> None:
    from hardware.circuitpython.device_builder import _pixel_kind

    assert _pixel_kind(_matrix_config().pixels[0]) == "matrix"


def test_pixel_kind_names_a_neopixel_config_neopixel() -> None:
    from hardware.circuitpython.device_builder import _pixel_kind

    assert _pixel_kind(_neopixel_config().pixels[0]) == "neopixel"


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
# build_hardware — pixels narration: one representative indexed pixels[n]
# line plus the absent-section case (#759). The full "ok"/"disabled" line
# text for every pixels[n] entry, including a mixed matrix-then-neopixel
# config's ordering, is now the comprehensive tests' job
# (test_device_builder.py, #852); the unknown-pin/no-I2C-bus FAILED
# attribution this file used to assert here is proven generically by
# hardware/shared/tests/test_build_narration.py and by the one retained
# integration attribution test (test_device_builder_buttons_logging.py),
# while the ValueError/RuntimeError themselves stay covered directly on
# _setup_neopixels/_setup_pixels above.
# ---------------------------------------------------------------------------


def test_build_hardware_pixels_entry_narrates_its_ok_line() -> None:
    config = _neopixel_config(scopes={"personal": {"pin": "D5", "count": 10}})
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "[hw] pixels[0] neopixel pin=D5 count=10 order=GRB scope=personal ok\n" in "".join(
        fragments
    )


def test_build_hardware_empty_pixels_list_produces_no_pixel_lines() -> None:
    config = _minimal_config()
    board_mock = _mock_board(D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "pixels[" not in "".join(fragments)

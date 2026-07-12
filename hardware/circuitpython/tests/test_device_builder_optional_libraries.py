"""Tests proving each per-component driver library in device_builder is
imported only inside the branch or setup helper that builds its component
(issue #690) -- mirroring the ``_make_writer``/``rp2pio`` import-probe prior
art (test_setup_ir_pio.py) for "library present vs. absent" coverage.

None of ``adafruit_is31fl3741``, ``neopixel``, ``pulseio``,
``audiobusio``/``audiocore``/``audiomixer``, or ``adafruit_drv2605`` are
actually pip-installed in this CPython test environment -- the sibling
conftest.py stubs them into ``sys.modules`` once per session so every *other*
test in this directory can import the hardware-adjacent modules that still
need them unconditionally at their own module scope (audio_output.py,
drv2605_output.py, is31fl3741_output.py). The tests here instead pop those
stubs for the duration of a single test -- simulating the library being
genuinely absent from a prop -- and restore them afterward so later tests in
the session are unaffected. "Library present" coverage for the same branches
lives in test_device_builder.py, unchanged apart from patch targets moving to
match the now-lazy imports.
"""

from __future__ import annotations

import sys
from contextlib import ExitStack, contextmanager
from unittest.mock import MagicMock, patch

from hardware.shared.device_config import parse_device_config


@contextmanager
def _library_absent(*module_names: str):
    """Remove *module_names* from ``sys.modules`` for the duration of the block.

    Restores whatever was previously registered (conftest's stub, if any)
    afterward, so popping a library here never leaks into later tests.
    """
    saved = {name: sys.modules.pop(name) for name in module_names if name in sys.modules}
    try:
        yield
    finally:
        for name in module_names:
            sys.modules.pop(name, None)
        sys.modules.update(saved)


def _mock_board(**pins):
    """Return a mock board module with the given pin attributes."""
    mock = MagicMock()
    for name, pin in pins.items():
        setattr(mock, name, pin)
    return mock


def _enter_baseline_patches(stack: ExitStack) -> None:
    """Patch every hardware setup helper not under test, so a bare config
    (no matrix, no NeoPixel, no audio, no ir) builds cleanly."""
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


def _bare_config():
    """A DeviceConfig with no pixels, no audio, and no ir -- every optional
    hardware section absent."""
    return parse_device_config({"pixels": [], "buttons": []})


# ---------------------------------------------------------------------------
# Importing the builder itself never pulls in a driver library
# ---------------------------------------------------------------------------


def test_importing_device_builder_does_not_import_any_driver_library() -> None:
    """A fresh import of device_builder -- the scenario a prop's boot code
    hits -- never touches a per-component driver library, only board, busio,
    digitalio, and microcontroller."""
    driver_libraries = (
        "adafruit_is31fl3741",
        "adafruit_is31fl3741.adafruit_rgbmatrixqt",
        "neopixel",
        "pulseio",
        "audiobusio",
        "audiocore",
        "audiomixer",
        "adafruit_drv2605",
    )

    with _library_absent("hardware.circuitpython.device_builder", *driver_libraries):
        import hardware.circuitpython.device_builder  # noqa: F401

        for name in driver_libraries:
            assert name not in sys.modules, f"importing device_builder pulled in {name}"


# ---------------------------------------------------------------------------
# Matrix branch: adafruit_is31fl3741 stays uninstalled with no matrix entry
# ---------------------------------------------------------------------------


def test_build_hardware_without_matrix_entry_succeeds_when_is31fl3741_uninstalled() -> None:
    config = _bare_config()
    board_mock = _mock_board()

    with (
        _library_absent("adafruit_is31fl3741", "adafruit_is31fl3741.adafruit_rgbmatrixqt"),
        ExitStack() as stack,
    ):
        _enter_baseline_patches(stack)

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    assert hw.outputs == []


# ---------------------------------------------------------------------------
# NeoPixel branch: neopixel stays uninstalled with no NeoPixel entry
# ---------------------------------------------------------------------------


def test_build_hardware_without_neopixel_entry_succeeds_when_neopixel_uninstalled() -> None:
    config = _bare_config()
    board_mock = _mock_board()

    with _library_absent("neopixel"), ExitStack() as stack:
        _enter_baseline_patches(stack)

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    assert hw.outputs == []


# ---------------------------------------------------------------------------
# Audio branch: the audio stack stays uninstalled with no audio section
# ---------------------------------------------------------------------------


def test_build_hardware_without_audio_section_succeeds_when_audio_stack_uninstalled() -> None:
    config = _bare_config()
    assert config.audio is None
    board_mock = _mock_board()

    with _library_absent("audiobusio", "audiocore", "audiomixer"), ExitStack() as stack:
        _enter_baseline_patches(stack)

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    assert hw.outputs == []


# ---------------------------------------------------------------------------
# IR branch: pulseio stays uninstalled with no ir section
# ---------------------------------------------------------------------------


def test_build_hardware_without_ir_section_succeeds_when_pulseio_uninstalled() -> None:
    config = _bare_config()
    assert config.ir is None
    board_mock = _mock_board()

    with _library_absent("pulseio"), ExitStack() as stack:
        _enter_baseline_patches(stack)

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    assert hw.ir_receiver is None


# ---------------------------------------------------------------------------
# Haptics-motor branch: _setup_drv2605's own presence probe already
# tolerates adafruit_drv2605 being absent (issue #690's "stays lazy"
# carve-out); Drv2605EffectOutput's import must move too, otherwise
# build_hardware would require the library just to run regardless.
# ---------------------------------------------------------------------------


def test_build_hardware_succeeds_when_drv2605_uninstalled() -> None:
    config = _bare_config()
    board_mock = _mock_board()

    with _library_absent("adafruit_drv2605"), ExitStack() as stack:
        stack.enter_context(patch("hardware.circuitpython.device_builder._setup_external_power"))
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_i2c",
                return_value=MagicMock(),
            )
        )
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_buttons",
                return_value=MagicMock(),
            )
        )
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_accelerometer",
                return_value=None,
            )
        )
        # _setup_drv2605 itself is intentionally left unpatched -- it must
        # run for real and hit its own internal ImportError probe.

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    assert hw.outputs == []

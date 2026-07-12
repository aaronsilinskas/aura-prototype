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
drv2605_output.py, is31fl3741_output.py). ``adafruit_lis3dh`` is never stubbed
at all -- nothing in this repo imports it unconditionally. The tests here
instead pop the stubbed libraries for the duration of a single test --
simulating the library being genuinely absent from a prop -- and restore them
afterward so later tests in the session are unaffected. "Library present"
coverage for the same branches lives in test_device_builder.py, unchanged
apart from patch targets moving to match the now-lazy imports.

Accelerometer and haptics are config-gated (issue #691): a config that
doesn't declare the section never imports the section's driver library,
mirroring the matrix/neopixel/audio/IR coverage below. A *declared* section
whose driver library is missing is a hard error -- covered separately below,
distinct from the "never touched when undeclared" cases.
"""

from __future__ import annotations

import sys
from contextlib import ExitStack, contextmanager

import pytest

from hardware.circuitpython.tests.test_device_builder import _enter_hw_patches, _mock_board
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


_bare_config_mapping = {"pixels": [], "buttons": []}


def _bare_config():
    """A DeviceConfig with no pixels, no audio, and no ir -- every optional
    hardware section absent."""
    return parse_device_config(_bare_config_mapping)


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
        "adafruit_lis3dh",
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
        _enter_hw_patches(stack)

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
        _enter_hw_patches(stack)

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
        _enter_hw_patches(stack)

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
        _enter_hw_patches(stack)

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    assert hw.ir_receiver is None


# ---------------------------------------------------------------------------
# Accelerometer branch: adafruit_lis3dh stays uninstalled with no
# accelerometer section (issue #691's config-gating)
# ---------------------------------------------------------------------------


def test_build_hardware_without_accelerometer_section_succeeds_when_lis3dh_uninstalled() -> None:
    config = _bare_config()
    assert config.accelerometer is None
    board_mock = _mock_board()

    with _library_absent("adafruit_lis3dh"), ExitStack() as stack:
        _enter_hw_patches(stack)

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    assert hw.accelerometer is None


def test_build_hardware_declared_accelerometer_raises_when_lis3dh_uninstalled() -> None:
    """A declared accelerometer whose driver library is missing is a hard
    error (issue #691) -- unlike the undeclared case above, this must reach
    the real `import adafruit_lis3dh` and let its ImportError propagate."""
    mapping = dict(_bare_config_mapping, accelerometer={})
    config = parse_device_config(mapping)
    board_mock = _mock_board()

    with _library_absent("adafruit_lis3dh"), ExitStack() as stack:
        # _setup_accelerometer itself is intentionally left unpatched -- it
        # must run for real and hit the missing import.
        _enter_hw_patches(stack, patch_accelerometer=False)

        from hardware.circuitpython.device_builder import build_hardware

        with pytest.raises(ImportError):
            build_hardware(config, board_module=board_mock)


# ---------------------------------------------------------------------------
# Haptics-motor branch: adafruit_drv2605 stays uninstalled with no haptics
# section (issue #691's config-gating); Drv2605EffectOutput's import must
# move too, otherwise build_hardware would require the library just to run
# regardless.
# ---------------------------------------------------------------------------


def test_build_hardware_without_haptics_section_succeeds_when_drv2605_uninstalled() -> None:
    config = _bare_config()
    assert config.haptics is None
    board_mock = _mock_board()

    with _library_absent("adafruit_drv2605"), ExitStack() as stack:
        _enter_hw_patches(stack)

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    assert hw.outputs == []


def test_build_hardware_declared_haptics_raises_when_drv2605_uninstalled() -> None:
    """A declared haptics section whose driver library is missing is a hard
    error (issue #691) -- unlike the undeclared case above, this must reach
    the real `import adafruit_drv2605` and let its ImportError propagate."""
    mapping = dict(_bare_config_mapping, haptics={})
    config = parse_device_config(mapping)
    board_mock = _mock_board()

    with _library_absent("adafruit_drv2605"), ExitStack() as stack:
        # _setup_drv2605 itself is intentionally left unpatched -- it must
        # run for real and hit the missing import.
        _enter_hw_patches(stack, patch_drv2605=False)

        from hardware.circuitpython.device_builder import build_hardware

        with pytest.raises(ImportError):
            build_hardware(config, board_module=board_mock)

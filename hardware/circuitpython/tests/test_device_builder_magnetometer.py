"""Tests for device_builder's magnetometer subsystem (issue #821).

Covers ``_setup_magnetometer`` directly (continuous-mode/data-rate
configuration, the one behaviour that diverges from ``_setup_accelerometer``'s
bare defaults) and the magnetometer slice of ``build_hardware`` (config-gated
wiring, hard-error cases, disabled/undeclared omission, and narration),
mirroring the accelerometer coverage in test_device_builder_audio_haptics.py.
"adafruit_mmc56x3" is never stubbed in conftest.py, mirroring "adafruit_lis3dh"
-- nothing in this repo imports it unconditionally -- so the direct
``_setup_magnetometer`` tests below inject a fake module into ``sys.modules``
for the duration of the test. "Library missing" coverage (the section
declared but ``adafruit_mmc56x3`` genuinely uninstalled) lives in
test_device_builder_optional_libraries.py, alongside the accelerometer/haptics
equivalents.
"""

from __future__ import annotations

import sys
import types
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest

from hardware.circuitpython.tests._hw_patch_mocks import (
    _enter_hw_patches,
    _minimal_config,
    _mock_board,
    _patch_neopixel,
    _recording_logger,
)
from hardware.shared.device_config import parse_device_config

# ---------------------------------------------------------------------------
# _setup_magnetometer — construct MMC5603 from an I2C bus, in continuous mode
# ---------------------------------------------------------------------------


# The raw-0 all-zero-register value _setup_magnetometer probes for -- what the real
# hardware streamed from a mis-wired MMC5603 that still ACKed the bus. Kept as the
# on-device literal (not imported from the module constant) so these tests pin the
# actual observed reading, and comfortably inside the module's detection tolerance.
_SENTINEL_UT = -3276.8
_LIVE_UT = (12.3, -4.5, 40.1)


class _FakeMmc5603:
    """Records the constructor's *i2c* plus whatever attributes are set on it
    afterward -- standing in for the real adafruit_mmc56x3.MMC5603, which
    isn't installed in this CPython test environment. Reads a live, non-sentinel
    field so ``_setup_magnetometer``'s raw-0 probe passes on the first poll."""

    def __init__(self, i2c: object) -> None:
        self.i2c = i2c
        self.data_rate: int | None = None
        self.continuous_mode: bool | None = None

    @property
    def magnetic(self) -> tuple[float, float, float]:
        return _LIVE_UT


class _DeadMmc5603(_FakeMmc5603):
    """A chip that ACKs the bus but never converts: every ``.magnetic`` poll
    reads the all-zero sentinel on every axis."""

    @property
    def magnetic(self) -> tuple[float, float, float]:
        return (_SENTINEL_UT, _SENTINEL_UT, _SENTINEL_UT)


class _SlowStartMmc5603(_FakeMmc5603):
    """A healthy chip whose first continuous-mode conversion hasn't landed yet:
    reads the sentinel for its first two polls, then a live field."""

    def __init__(self, i2c: object) -> None:
        super().__init__(i2c)
        self._polls = 0

    @property
    def magnetic(self) -> tuple[float, float, float]:
        self._polls += 1
        if self._polls <= 2:
            return (_SENTINEL_UT, _SENTINEL_UT, _SENTINEL_UT)
        return _LIVE_UT


def _install_fake_mmc56x3(mmc5603_cls: type):
    """Context manager installing a fake adafruit_mmc56x3 whose ``MMC5603`` is
    *mmc5603_cls*, restoring whatever (if anything) was there before."""
    fake_module = types.ModuleType("adafruit_mmc56x3")
    fake_module.MMC5603 = mmc5603_cls  # type: ignore[attr-defined]
    return patch.dict(sys.modules, {"adafruit_mmc56x3": fake_module})


@pytest.fixture
def _fake_mmc56x3_module():
    """Install a fake adafruit_mmc56x3 module for the duration of a test,
    restoring whatever (if anything) was there before -- mirrors
    ``_library_absent``'s save/restore shape from
    test_device_builder_optional_libraries.py, but installing rather than
    removing, since this module is never present at all."""
    fake_module = types.ModuleType("adafruit_mmc56x3")
    fake_module.MMC5603 = _FakeMmc5603  # type: ignore[attr-defined]
    with patch.dict(sys.modules, {"adafruit_mmc56x3": fake_module}):
        yield fake_module


def test_setup_magnetometer_returns_the_constructed_mmc5603(_fake_mmc56x3_module) -> None:
    fake_i2c = MagicMock(name="i2c")

    from hardware.circuitpython.device_builder import _setup_magnetometer

    result = _setup_magnetometer(fake_i2c)

    assert isinstance(result, _FakeMmc5603)
    assert result.i2c is fake_i2c


def test_setup_magnetometer_puts_the_chip_in_continuous_mode_at_100hz(
    _fake_mmc56x3_module,
) -> None:
    """The one behaviour that diverges from _setup_accelerometer's bare
    defaults: the MMC5603's default one-shot mode makes each .magnetic read
    busy-wait, so the builder must configure a fixed data rate and flip on
    continuous mode before returning the chip."""
    from hardware.circuitpython.device_builder import _setup_magnetometer

    result = _setup_magnetometer(MagicMock(name="i2c"))

    assert result.data_rate == 100
    assert result.continuous_mode is True


def test_setup_magnetometer_raises_when_chip_only_reads_all_zero_sentinel() -> None:
    """A chip that ACKs the bus but never converts reads the all-zero sentinel
    on every axis forever. ``MMC5603(i2c)`` construction cannot catch this, so
    the builder probes and turns it into the same loud wiring fault every other
    peripheral raises rather than streaming -3276.8 as if it were field data."""
    from hardware.circuitpython.device_builder import _setup_magnetometer

    with (
        _install_fake_mmc56x3(_DeadMmc5603),
        patch("hardware.circuitpython.device_builder.time.sleep"),  # don't burn the probe window
        pytest.raises(RuntimeError, match="power and ground"),
    ):
        _setup_magnetometer(MagicMock(name="i2c"))


def test_setup_magnetometer_waits_for_the_first_conversion_before_giving_up() -> None:
    """The probe must not fail a healthy chip whose first continuous-mode
    conversion simply hasn't landed yet: reading the sentinel on early polls is
    expected, so it keeps polling and returns the chip once a live value
    appears."""
    from hardware.circuitpython.device_builder import _setup_magnetometer

    with (
        _install_fake_mmc56x3(_SlowStartMmc5603),
        patch("hardware.circuitpython.device_builder.time.sleep"),
    ):
        result = _setup_magnetometer(MagicMock(name="i2c"))

    assert isinstance(result, _SlowStartMmc5603)
    assert result.magnetic == _LIVE_UT


# ---------------------------------------------------------------------------
# build_hardware — magnetometer is config-gated, not presence-probed,
# mirroring the accelerometer (#691)
# ---------------------------------------------------------------------------


def _neopixel_config_with_magnetometer():
    mapping = {
        "pixels": [{"type": "neopixel", "scopes": {"personal": {"pin": "D5", "count": 10}}}],
        "buttons": ["D9"],
        "magnetometer": {},
    }
    return parse_device_config(mapping)


def test_build_hardware_magnetometer_section_builds_magnetometer_onto_bundle() -> None:
    config = _neopixel_config_with_magnetometer()
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())
    mock_magnetometer = MagicMock()

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_magnetometer",
                return_value=mock_magnetometer,
            )
        )
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    assert hw.magnetometer is mock_magnetometer


def test_build_hardware_declared_magnetometer_with_no_i2c_bus_raises_runtime_error() -> None:
    """A declared magnetometer whose bus can't be reached is a hard error,
    mirroring the accelerometer's no-I2C-bus case -- absence must be
    expressed by omitting the section, not a silent probe failure."""
    config = _neopixel_config_with_magnetometer()
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())

    with ExitStack() as stack:
        stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_i2c", return_value=None)
        )
        stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_buttons", return_value=MagicMock())
        )
        mock_setup_magnetometer = stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_magnetometer")
        )
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        with pytest.raises(RuntimeError, match="magnetometer"):
            build_hardware(config, board_module=board_mock)

    mock_setup_magnetometer.assert_not_called()


def test_build_hardware_declared_magnetometer_raises_when_chip_not_found() -> None:
    """A declared magnetometer whose chip can't be constructed on an
    available bus is a hard error too -- not just the no-I2C-bus case."""
    config = _neopixel_config_with_magnetometer()
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())

    with ExitStack() as stack:
        _enter_hw_patches(stack, patch_magnetometer=False)
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_magnetometer",
                side_effect=ValueError("no MMC5603 found"),
            )
        )
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        with pytest.raises(ValueError, match="no MMC5603 found"):
            build_hardware(config, board_module=board_mock)


def test_build_hardware_disabled_magnetometer_section_omits_magnetometer_from_bundle() -> None:
    """``magnetometer: {enabled: false}`` is neither built nor probed."""
    config = _neopixel_config_with_magnetometer()
    config.magnetometer.enabled = False
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())

    with ExitStack() as stack:
        mocks = _enter_hw_patches(stack)
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    assert hw.magnetometer is None
    mocks.magnetometer.assert_not_called()


def test_build_hardware_enabled_magnetometer_with_disabled_i2c_raises_runtime_error() -> None:
    """``i2c: {enabled: false}`` builds no bus at all, so a magnetometer left
    enabled hits the same declared-and-enabled-but-unreachable hard error as
    a missing i2c section."""
    mapping = {
        "pixels": [{"type": "neopixel", "scopes": {"personal": {"pin": "D5", "count": 10}}}],
        "buttons": ["D9"],
        "i2c": {"sda": "GP4", "scl": "GP5", "enabled": False},
        "magnetometer": {},
    }
    config = parse_device_config(mapping)
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())

    with ExitStack() as stack:
        stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_buttons", return_value=MagicMock())
        )
        mock_setup_magnetometer = stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_magnetometer")
        )
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        with pytest.raises(RuntimeError, match="magnetometer"):
            build_hardware(config, board_module=board_mock)

    mock_setup_magnetometer.assert_not_called()


def test_build_hardware_magnetometer_not_probed_when_undeclared() -> None:
    """Presence-probing is gone: even with an I2C bus available, an
    undeclared magnetometer section is never probed -- absence is expressed
    by omitting the section, not a probe failure."""
    config = parse_device_config(
        {
            "pixels": [{"type": "neopixel", "scopes": {"personal": {"pin": "D5", "count": 10}}}],
            "buttons": ["D9"],
        }
    )
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())
    available_i2c = MagicMock(name="available_i2c")

    with ExitStack() as stack:
        stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_i2c", return_value=available_i2c)
        )
        mock_setup_magnetometer = stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_magnetometer")
        )
        stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_buttons", return_value=MagicMock())
        )
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    mock_setup_magnetometer.assert_not_called()
    assert hw.magnetometer is None


# ---------------------------------------------------------------------------
# build_hardware — magnetometer narration, mirroring accelerometer/haptics
# ---------------------------------------------------------------------------


def test_build_hardware_logs_magnetometer_ok_line_when_enabled_and_built() -> None:
    config = _neopixel_config_with_magnetometer()
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "[hw] magnetometer mmc5603 ok\n" in "".join(fragments)


def test_build_hardware_logs_magnetometer_disabled_line_when_section_disabled() -> None:
    config = _neopixel_config_with_magnetometer()
    config.magnetometer.enabled = False
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "[hw] magnetometer mmc5603 disabled\n" in "".join(fragments)


def test_build_hardware_logs_no_magnetometer_line_when_section_absent() -> None:
    config = _minimal_config()
    board_mock = _mock_board(D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "magnetometer" not in "".join(fragments)


def test_build_hardware_magnetometer_no_i2c_bus_marks_its_own_line_failed_and_propagates() -> None:
    """A declared-and-enabled magnetometer with no I2C bus available raises
    via _require_i2c -- the failure must close the magnetometer's own open
    line, not whichever line closed just before it (mirrors the
    accelerometer/haptics FAILED tests for the #758 spine)."""
    config = _neopixel_config_with_magnetometer()
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_i2c", return_value=None)
        )
        stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_buttons", return_value=MagicMock())
        )
        stack.enter_context(patch("hardware.circuitpython.device_builder._setup_magnetometer"))
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        with pytest.raises(RuntimeError, match="magnetometer"):
            build_hardware(config, board_module=board_mock, logger=logger)

    lines = "".join(fragments).splitlines(keepends=True)
    assert lines[-1] == "[hw] magnetometer mmc5603 FAILED\n"

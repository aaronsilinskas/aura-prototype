"""Tests for device_builder's sdcard subsystem: ``_setup_sdcard`` and the
sdcard slice of ``build_hardware``. Mirrors test_device_builder_radio_ir.py's
radio coverage -- sdcard is config-gated on the shared SPI bus the same way
radio is (#793).

Shared config-shape helpers and hardware patches come from
_hw_patch_mocks.py (#775).
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
from hardware.shared.device_config import parse_device_config
from hardware.shared.device_storage import DeviceStorage

# ---------------------------------------------------------------------------
# build_hardware -- sdcard is config-gated on spi, mirroring radio (#793)
# ---------------------------------------------------------------------------


def _neopixel_config_with_sdcard(enabled: bool | None = None):
    sdcard: dict[str, object] = {"cs": "D24", "mount": "/sd"}
    if enabled is not None:
        sdcard["enabled"] = enabled
    mapping = {
        "pixels": [{"type": "neopixel", "scopes": {"personal": {"pin": "D5", "count": 10}}}],
        "buttons": ["D9"],
        "spi": {"sck": "SCK", "mosi": "MOSI", "miso": "MISO"},
        "sdcard": sdcard,
    }
    return parse_device_config(mapping)


def test_build_hardware_sdcard_section_builds_device_storage_onto_bundle() -> None:
    config = _neopixel_config_with_sdcard()
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())
    mock_storage = MagicMock(name="sdcard_storage")

    with ExitStack() as stack:
        _enter_hw_patches(stack, patch_sdcard=False)
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_sdcard",
                return_value=mock_storage,
            )
        )
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    assert hw.storage is mock_storage


def test_build_hardware_declared_sdcard_with_no_spi_bus_raises_runtime_error() -> None:
    """A declared sdcard whose SPI bus can't be reached is a hard error,
    mirroring the radio-with-no-SPI-bus case -- absence must be expressed by
    omitting the section, not a silent probe failure."""
    config = _neopixel_config_with_sdcard()
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())

    with ExitStack() as stack:
        stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_i2c", return_value=MagicMock())
        )
        stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_spi", return_value=None)
        )
        stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_buttons", return_value=MagicMock())
        )
        mock_setup_sdcard = stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_sdcard")
        )
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        with pytest.raises(RuntimeError, match="sdcard"):
            build_hardware(config, board_module=board_mock)

    mock_setup_sdcard.assert_not_called()


def test_build_hardware_declared_sdcard_raises_when_card_unmountable() -> None:
    """A declared sdcard whose card can't be mounted on an available bus is
    a hard error too -- not just the no-SPI-bus case."""
    config = _neopixel_config_with_sdcard()
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())

    with ExitStack() as stack:
        _enter_hw_patches(stack, patch_sdcard=False)
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_sdcard",
                side_effect=RuntimeError("sdcard section is declared but the card ... "),
            )
        )
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        with pytest.raises(RuntimeError, match="sdcard"):
            build_hardware(config, board_module=board_mock)


def test_build_hardware_disabled_sdcard_section_omits_storage_from_bundle() -> None:
    """``sdcard: {enabled: false}`` is neither built nor probed, mirroring
    every other component's enabled toggle."""
    config = _neopixel_config_with_sdcard(enabled=False)
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())

    with ExitStack() as stack:
        mocks = _enter_hw_patches(stack)
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    assert hw.storage is None
    mocks.sdcard.assert_not_called()


def test_build_hardware_without_sdcard_section_leaves_storage_none() -> None:
    config = _neopixel_config()
    board_mock = _mock_board(D5=MagicMock(), D6=MagicMock(), D9=MagicMock())

    with ExitStack() as stack:
        mocks = _enter_hw_patches(stack)
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    assert hw.storage is None
    mocks.sdcard.assert_not_called()


# ---------------------------------------------------------------------------
# _setup_sdcard -- resolves the sdcard cs pin and delegates to SdCardStorage
# ---------------------------------------------------------------------------


def test_setup_sdcard_resolves_cs_as_a_raw_pin_and_delegates_to_storage() -> None:
    """Unlike _setup_radio's cs, which is wrapped in digitalio.DigitalInOut,
    sdcardio.SDCard takes the raw resolved microcontroller.Pin directly."""
    sdcard_cfg = parse_device_config(
        {"buttons": [], "sdcard": {"cs": "D24", "mount": "/sd"}}
    ).sdcard
    cs_pin = MagicMock(name="cs_pin")
    board_mock = _mock_board(D24=cs_pin)
    spi = MagicMock(name="spi")
    mock_storage = MagicMock(name="storage")

    with patch(
        "hardware.circuitpython.sdcard_storage.SdCardStorage",
        return_value=mock_storage,
    ) as mock_storage_cls:
        from hardware.circuitpython.device_builder import _setup_sdcard

        result = _setup_sdcard(spi, sdcard_cfg, board_mock)

    mock_storage_cls.assert_called_once_with(spi, cs_pin, "/sd")
    assert result is mock_storage


def test_setup_sdcard_wraps_mount_os_error_naming_section_cs_and_mount() -> None:
    sdcard_cfg = parse_device_config(
        {"buttons": [], "sdcard": {"cs": "D24", "mount": "/sd"}}
    ).sdcard
    board_mock = _mock_board(D24=MagicMock())
    spi = MagicMock(name="spi")

    with patch(
        "hardware.circuitpython.sdcard_storage.SdCardStorage",
        side_effect=OSError("no SD card"),
    ):
        from hardware.circuitpython.device_builder import _setup_sdcard

        with pytest.raises(RuntimeError, match=r"sdcard.*cs=D24.*mount=/sd") as excinfo:
            _setup_sdcard(spi, sdcard_cfg, board_mock)

    assert isinstance(excinfo.value.__cause__, OSError)


def test_setup_sdcard_returns_a_device_storage() -> None:
    sdcard_cfg = parse_device_config(
        {"buttons": [], "sdcard": {"cs": "D24", "mount": "/sd"}}
    ).sdcard
    board_mock = _mock_board(D24=MagicMock())
    spi = MagicMock(name="spi")

    with (
        patch("hardware.circuitpython.sdcard_storage.sdcardio.SDCard"),
        patch("hardware.circuitpython.sdcard_storage.storage.VfsFat"),
        patch("hardware.circuitpython.sdcard_storage.storage.mount"),
    ):
        from hardware.circuitpython.device_builder import _setup_sdcard

        result = _setup_sdcard(spi, sdcard_cfg, board_mock)

    assert isinstance(result, DeviceStorage)


# ---------------------------------------------------------------------------
# build_hardware -- sdcard narration (#793). One representative "ok" line
# plus the absent-section case; "disabled" is covered by the all-disabled
# comprehensive test, and the no-SPI-bus/unmountable-card FAILED cases are
# proven generically by the primitive's own tests plus the non-narration
# raises tests above and the one retained integration attribution test
# (test_device_builder.py / test_device_builder_buttons_logging.py, #852).
# ---------------------------------------------------------------------------


def test_build_hardware_logs_sdcard_ok_line_when_enabled_and_mounted() -> None:
    config = _neopixel_config_with_sdcard()
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack, patch_sdcard=False)
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_sdcard",
                return_value=MagicMock(),
            )
        )
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "[hw] sdcard mount=/sd cs=D24 ok\n" in "".join(fragments)


def test_build_hardware_logs_no_sdcard_line_when_section_absent() -> None:
    config = _minimal_config()
    board_mock = _mock_board(D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "sdcard" not in "".join(fragments)

"""Behaviour-driven tests for SdCardStorage (hardware/circuitpython/sdcard_storage.py).

``sdcardio``/``storage`` are stubbed into ``sys.modules`` by the sibling
conftest.py so this suite runs under CPython; the SDCard/VfsFat classes and
mount() function are MagicMocks substituted per test via ``patch``.
"""

from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_storage(mount: str = "/sd"):
    """Return an SdCardStorage plus the mocks its construction touched."""
    with (
        patch("hardware.circuitpython.sdcard_storage.sdcardio.SDCard") as mock_sdcard_cls,
        patch("hardware.circuitpython.sdcard_storage.storage.VfsFat") as mock_vfsfat_cls,
        patch("hardware.circuitpython.sdcard_storage.storage.mount") as mock_mount,
    ):
        mock_card = MagicMock(name="card")
        mock_sdcard_cls.return_value = mock_card
        mock_vfs = MagicMock(name="vfs")
        mock_vfsfat_cls.return_value = mock_vfs

        from hardware.circuitpython.sdcard_storage import SdCardStorage

        storage_instance = SdCardStorage(
            spi=MagicMock(name="spi"), cs=MagicMock(name="cs"), mount=mount
        )

        return storage_instance, mock_sdcard_cls, mock_vfsfat_cls, mock_mount, mock_card, mock_vfs


# ---------------------------------------------------------------------------
# construction -- mounts the card
# ---------------------------------------------------------------------------


def test_construction_builds_sdcard_from_given_spi_and_cs() -> None:
    spi = MagicMock(name="spi")
    cs = MagicMock(name="cs")

    with (
        patch("hardware.circuitpython.sdcard_storage.sdcardio.SDCard") as mock_sdcard_cls,
        patch("hardware.circuitpython.sdcard_storage.storage.VfsFat"),
        patch("hardware.circuitpython.sdcard_storage.storage.mount"),
    ):
        from hardware.circuitpython.sdcard_storage import SdCardStorage

        SdCardStorage(spi=spi, cs=cs, mount="/sd")

    mock_sdcard_cls.assert_called_once_with(spi, cs)


def test_construction_mounts_the_card_as_writable_fat_filesystem() -> None:
    _, _, mock_vfsfat_cls, mock_mount, mock_card, mock_vfs = _build_storage(mount="/sd")

    mock_vfsfat_cls.assert_called_once_with(mock_card)
    mock_mount.assert_called_once_with(mock_vfs, "/sd", readonly=False)


# ---------------------------------------------------------------------------
# resulting instance -- behaves as a DeviceStorage against the mount point
# ---------------------------------------------------------------------------


def test_sdcard_storage_is_a_device_storage_rooted_at_the_mount_point() -> None:
    storage_instance, *_ = _build_storage(mount="/sd")

    assert storage_instance.path("state.json") == "/sd/state.json"


def test_construction_propagates_mount_failure_as_the_raw_os_error() -> None:
    """No wrapping happens here -- device_builder._setup_sdcard is the layer
    that catches this OSError and wraps it in a section-named RuntimeError."""
    with (
        patch("hardware.circuitpython.sdcard_storage.sdcardio.SDCard") as mock_sdcard_cls,
        patch("hardware.circuitpython.sdcard_storage.storage.VfsFat"),
        patch("hardware.circuitpython.sdcard_storage.storage.mount") as mock_mount,
    ):
        mock_sdcard_cls.return_value = MagicMock()
        mock_mount.side_effect = OSError("no SD card")

        from hardware.circuitpython.sdcard_storage import SdCardStorage

        with pytest.raises(OSError, match="no SD card"):
            SdCardStorage(spi=MagicMock(), cs=MagicMock(), mount="/sd")

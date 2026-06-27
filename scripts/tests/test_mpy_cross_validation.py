"""Tests for mpy-cross version validation against the device's CircuitPython version."""

from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.build import (
    EXPECTED_CIRCUITPYTHON_MAJOR,
    VersionError,
    get_mpy_cross_major,
    parse_circuitpython_major_from_boot_out,
    validate_mpy_cross_version,
)

# ---------------------------------------------------------------------------
# parse_circuitpython_major_from_boot_out
# ---------------------------------------------------------------------------


def test_parses_major_version_from_standard_boot_out() -> None:
    boot_out = "Adafruit CircuitPython 10.2.1 on 2025-01-15; Adafruit Feather RP2040"
    assert parse_circuitpython_major_from_boot_out(boot_out) == 10


def test_parses_major_version_from_different_major() -> None:
    boot_out = "Adafruit CircuitPython 9.1.0 on 2024-06-01; Adafruit Feather M4"
    assert parse_circuitpython_major_from_boot_out(boot_out) == 9


def test_parses_major_version_when_extra_lines_present() -> None:
    boot_out = (
        "Adafruit CircuitPython 10.0.0-beta.1 on 2025-03-01; Some Board\nBoard ID: some-board\n"
    )
    assert parse_circuitpython_major_from_boot_out(boot_out) == 10


def test_raises_version_error_when_boot_out_has_no_circuitpython_line() -> None:
    boot_out = "something unexpected"
    with pytest.raises(VersionError, match=r"boot_out\.txt"):
        parse_circuitpython_major_from_boot_out(boot_out)


# ---------------------------------------------------------------------------
# get_mpy_cross_major
# ---------------------------------------------------------------------------


def test_returns_major_version_from_mpy_cross_output() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = b"mpy-cross 10.2.1\n"
        assert get_mpy_cross_major("mpy-cross") == 10


def test_parses_major_version_for_different_release() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = b"mpy-cross 9.0.0\n"
        assert get_mpy_cross_major("mpy-cross") == 9


def test_raises_version_error_when_mpy_cross_not_found() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = FileNotFoundError("mpy-cross not found")
        with pytest.raises(VersionError, match="mpy-cross"):
            get_mpy_cross_major("mpy-cross")


def test_raises_version_error_when_mpy_cross_output_is_unparseable() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = b"something unexpected\n"
        with pytest.raises(VersionError, match="mpy-cross"):
            get_mpy_cross_major("mpy-cross")


def test_raises_version_error_when_mpy_cross_exits_nonzero() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 1
        mock_run.return_value.stderr = b"some error\n"
        with pytest.raises(VersionError, match="mpy-cross"):
            get_mpy_cross_major("mpy-cross")


# ---------------------------------------------------------------------------
# validate_mpy_cross_version — with device (boot_out.txt present)
# ---------------------------------------------------------------------------


def test_matching_mpy_cross_and_device_version_does_not_raise(tmp_path: Path) -> None:
    mount = tmp_path / "mount"
    mount.mkdir()
    (mount / "boot_out.txt").write_text(
        "Adafruit CircuitPython 10.2.1 on 2025-01-15; Adafruit Feather RP2040"
    )
    with patch("scripts.build.get_mpy_cross_major", return_value=10):
        validate_mpy_cross_version(mount=mount, mpy_cross_bin="mpy-cross")


def test_mismatched_major_version_raises_version_error(tmp_path: Path) -> None:
    mount = tmp_path / "mount"
    mount.mkdir()
    (mount / "boot_out.txt").write_text(
        "Adafruit CircuitPython 10.2.1 on 2025-01-15; Adafruit Feather RP2040"
    )
    with (
        patch("scripts.build.get_mpy_cross_major", return_value=9),
        pytest.raises(VersionError, match="mpy-cross"),
    ):
        validate_mpy_cross_version(mount=mount, mpy_cross_bin="mpy-cross")


def test_version_error_message_includes_both_versions(tmp_path: Path) -> None:
    mount = tmp_path / "mount"
    mount.mkdir()
    (mount / "boot_out.txt").write_text(
        "Adafruit CircuitPython 10.2.1 on 2025-01-15; Adafruit Feather RP2040"
    )
    with patch("scripts.build.get_mpy_cross_major", return_value=9):
        with pytest.raises(VersionError) as exc_info:
            validate_mpy_cross_version(mount=mount, mpy_cross_bin="mpy-cross")
        assert "9" in str(exc_info.value)
        assert "10" in str(exc_info.value)


def test_missing_boot_out_txt_raises_version_error(tmp_path: Path) -> None:
    mount = tmp_path / "mount"
    mount.mkdir()
    # No boot_out.txt
    with (
        patch("scripts.build.get_mpy_cross_major", return_value=10),
        pytest.raises(VersionError, match=r"boot_out\.txt"),
    ):
        validate_mpy_cross_version(mount=mount, mpy_cross_bin="mpy-cross")


# ---------------------------------------------------------------------------
# validate_mpy_cross_version — dry-run / CI (no device, mount=None)
# ---------------------------------------------------------------------------


def test_dry_run_matching_mpy_cross_and_expected_version_does_not_raise() -> None:
    with patch("scripts.build.get_mpy_cross_major", return_value=EXPECTED_CIRCUITPYTHON_MAJOR):
        validate_mpy_cross_version(mount=None, mpy_cross_bin="mpy-cross")


def test_dry_run_mismatched_mpy_cross_and_expected_version_raises_version_error() -> None:
    wrong_major = EXPECTED_CIRCUITPYTHON_MAJOR + 1
    with (
        patch("scripts.build.get_mpy_cross_major", return_value=wrong_major),
        pytest.raises(VersionError, match="mpy-cross"),
    ):
        validate_mpy_cross_version(mount=None, mpy_cross_bin="mpy-cross")


def test_dry_run_version_error_message_mentions_expected_version() -> None:
    wrong_major = EXPECTED_CIRCUITPYTHON_MAJOR + 1
    with patch("scripts.build.get_mpy_cross_major", return_value=wrong_major):
        with pytest.raises(VersionError) as exc_info:
            validate_mpy_cross_version(mount=None, mpy_cross_bin="mpy-cross")
        assert str(EXPECTED_CIRCUITPYTHON_MAJOR) in str(exc_info.value)


# ---------------------------------------------------------------------------
# EXPECTED_CIRCUITPYTHON_MAJOR constant
# ---------------------------------------------------------------------------


def test_expected_circuitpython_major_matches_setup_script_default() -> None:
    # setup_mpy_cross.sh defaults to 10.2.1 → major = 10
    assert EXPECTED_CIRCUITPYTHON_MAJOR == 10

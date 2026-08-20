"""Behaviour-driven tests for the DeviceStorage port (hardware/shared/device_storage.py).

Also exercises FakeDeviceStorage (hardware/shared/tests/helpers.py), the in-memory
double, against the same observable contract so the two stay interchangeable.
"""

import builtins
import errno
import json
import os

import pytest

from hardware.shared.device_storage import DeviceStorage
from hardware.shared.tests.helpers import FakeDeviceStorage

ESCAPING_NAMES = ["../secret.txt", "scenes/../../secret.txt", "/etc/passwd"]


def _break_temp_file_writes(monkeypatch):
    """Make writing to a ``.tmp`` sibling fail, simulating a mid-write disk failure."""
    real_open = builtins.open

    def flaky_open(path, mode="r", *args, **kwargs):
        if str(path).endswith(".tmp") and "w" in mode:
            raise OSError("simulated disk full")
        return real_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", flaky_open)


# ---------------------------------------------------------------------------
# DeviceStorage — read_bytes / write_bytes round-trip
# ---------------------------------------------------------------------------


def test_read_bytes_returns_none_for_a_never_written_name(tmp_path):
    storage = DeviceStorage(str(tmp_path))

    assert storage.read_bytes("state.json") is None


def test_write_bytes_then_read_bytes_round_trips_exact_bytes(tmp_path):
    storage = DeviceStorage(str(tmp_path))

    storage.write_bytes("state.json", b"\x00\x01hello\xff")

    assert storage.read_bytes("state.json") == b"\x00\x01hello\xff"


def test_write_bytes_replaces_prior_content_entirely(tmp_path):
    storage = DeviceStorage(str(tmp_path))
    storage.write_bytes("state.json", b"original-content")

    storage.write_bytes("state.json", b"new")

    assert storage.read_bytes("state.json") == b"new"


def test_read_bytes_propagates_an_open_error_other_than_missing_file(tmp_path, monkeypatch):
    storage = DeviceStorage(str(tmp_path))

    def flaky_open(path, mode="rb", *args, **kwargs):
        raise OSError(errno.EACCES, "permission denied")

    monkeypatch.setattr(builtins, "open", flaky_open)

    with pytest.raises(OSError):
        storage.read_bytes("state.json")


# ---------------------------------------------------------------------------
# DeviceStorage — atomic-replace semantics
# ---------------------------------------------------------------------------


def test_failed_write_bytes_leaves_prior_content_intact(tmp_path, monkeypatch):
    storage = DeviceStorage(str(tmp_path))
    storage.write_bytes("state.json", b"original-content")

    _break_temp_file_writes(monkeypatch)

    with pytest.raises(OSError):
        storage.write_bytes("state.json", b"content-that-never-lands")

    monkeypatch.undo()
    assert storage.read_bytes("state.json") == b"original-content"


def test_write_bytes_leaves_no_temp_file_behind_after_success(tmp_path):
    storage = DeviceStorage(str(tmp_path))

    storage.write_bytes("state.json", b"data")

    assert sorted(os.listdir(tmp_path)) == ["state.json"]


def test_write_bytes_propagates_a_remove_error_other_than_missing_target(tmp_path, monkeypatch):
    storage = DeviceStorage(str(tmp_path))
    storage.write_bytes("state.json", b"original-content")

    def flaky_remove(path):
        raise OSError(errno.EACCES, "permission denied")

    monkeypatch.setattr(os, "remove", flaky_remove)

    with pytest.raises(OSError):
        storage.write_bytes("state.json", b"content-that-never-lands")

    monkeypatch.undo()
    assert storage.read_bytes("state.json") == b"original-content"


def test_write_bytes_propagates_a_mkdir_error_other_than_already_exists(tmp_path, monkeypatch):
    storage = DeviceStorage(str(tmp_path))

    def flaky_mkdir(path):
        raise OSError(errno.EACCES, "permission denied")

    monkeypatch.setattr(os, "mkdir", flaky_mkdir)

    with pytest.raises(OSError):
        storage.write_bytes("scenes/tag/state.json", b"data")


# ---------------------------------------------------------------------------
# DeviceStorage — subpaths
# ---------------------------------------------------------------------------


def test_write_bytes_auto_creates_missing_parent_directories(tmp_path):
    storage = DeviceStorage(str(tmp_path))

    storage.write_bytes("scenes/tag/state.json", b"tag-state")

    assert storage.read_bytes("scenes/tag/state.json") == b"tag-state"


def test_write_bytes_tolerates_already_present_parent_directories(tmp_path):
    storage = DeviceStorage(str(tmp_path))
    storage.write_bytes("scenes/tag/state.json", b"first")

    storage.write_bytes("scenes/tag/other.json", b"second")

    assert storage.read_bytes("scenes/tag/other.json") == b"second"


# ---------------------------------------------------------------------------
# DeviceStorage — escape rejection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("escaping_name", ESCAPING_NAMES)
def test_read_bytes_rejects_a_name_that_escapes_the_mount_root(tmp_path, escaping_name):
    storage = DeviceStorage(str(tmp_path))

    with pytest.raises(ValueError):
        storage.read_bytes(escaping_name)


@pytest.mark.parametrize("escaping_name", ESCAPING_NAMES)
def test_write_bytes_rejects_a_name_that_escapes_the_mount_root(tmp_path, escaping_name):
    storage = DeviceStorage(str(tmp_path))

    with pytest.raises(ValueError):
        storage.write_bytes(escaping_name, b"data")


@pytest.mark.parametrize("escaping_subpath", ESCAPING_NAMES)
def test_path_rejects_a_subpath_that_escapes_the_mount_root(tmp_path, escaping_subpath):
    storage = DeviceStorage(str(tmp_path))

    with pytest.raises(ValueError):
        storage.path(escaping_subpath)


def test_write_bytes_rejecting_an_escaping_name_leaves_no_file_written(tmp_path):
    storage = DeviceStorage(str(tmp_path))

    with pytest.raises(ValueError):
        storage.write_bytes("../secret.txt", b"data")

    assert os.listdir(tmp_path) == []


# ---------------------------------------------------------------------------
# DeviceStorage — path()
# ---------------------------------------------------------------------------


def test_path_returns_a_resolved_path_under_the_mount_root(tmp_path):
    storage = DeviceStorage(str(tmp_path))

    resolved = storage.path("scenes/tag/state.json")

    assert resolved == str(tmp_path) + "/scenes/tag/state.json"


def test_path_creates_no_directories(tmp_path):
    storage = DeviceStorage(str(tmp_path))

    storage.path("scenes/tag/state.json")

    assert not os.path.isdir(tmp_path / "scenes")


# ---------------------------------------------------------------------------
# DeviceStorage — mount_root
# ---------------------------------------------------------------------------


def test_mount_root_strips_trailing_slash_passed_to_constructor(tmp_path):
    storage = DeviceStorage(str(tmp_path) + "/")

    assert storage.mount_root == str(tmp_path)


def test_mount_root_omits_the_trailing_slash_that_path_of_empty_string_includes(tmp_path):
    storage = DeviceStorage(str(tmp_path))

    assert storage.mount_root == str(tmp_path)
    assert storage.path("") == str(tmp_path) + "/"


# ---------------------------------------------------------------------------
# DeviceStorage — read_json / write_json
# ---------------------------------------------------------------------------


def test_read_json_returns_none_for_a_never_written_name(tmp_path):
    storage = DeviceStorage(str(tmp_path))

    assert storage.read_json("state.json") is None


def test_write_json_then_read_json_round_trips_a_mapping(tmp_path):
    storage = DeviceStorage(str(tmp_path))

    storage.write_json("state.json", {"scene": "tag", "score": 3})

    assert storage.read_json("state.json") == {"scene": "tag", "score": 3}


def test_write_json_replaces_prior_content_entirely(tmp_path):
    storage = DeviceStorage(str(tmp_path))
    storage.write_json("state.json", {"scene": "tag"})

    storage.write_json("state.json", {"scene": "rlgl"})

    assert storage.read_json("state.json") == {"scene": "rlgl"}


def test_read_json_raises_on_malformed_content(tmp_path):
    storage = DeviceStorage(str(tmp_path))
    storage.write_bytes("state.json", b"{not valid json")

    with pytest.raises(json.JSONDecodeError):
        storage.read_json("state.json")


@pytest.mark.parametrize("escaping_name", ESCAPING_NAMES)
def test_read_json_rejects_a_name_that_escapes_the_mount_root(tmp_path, escaping_name):
    storage = DeviceStorage(str(tmp_path))

    with pytest.raises(ValueError):
        storage.read_json(escaping_name)


@pytest.mark.parametrize("escaping_name", ESCAPING_NAMES)
def test_write_json_rejects_a_name_that_escapes_the_mount_root(tmp_path, escaping_name):
    storage = DeviceStorage(str(tmp_path))

    with pytest.raises(ValueError):
        storage.write_json(escaping_name, {"scene": "tag"})


def test_failed_write_json_leaves_prior_content_intact(tmp_path, monkeypatch):
    storage = DeviceStorage(str(tmp_path))
    storage.write_json("state.json", {"scene": "tag"})

    _break_temp_file_writes(monkeypatch)

    with pytest.raises(OSError):
        storage.write_json("state.json", {"scene": "rlgl"})

    monkeypatch.undo()
    assert storage.read_json("state.json") == {"scene": "tag"}


# ---------------------------------------------------------------------------
# FakeDeviceStorage — in-memory test double (hardware/shared/tests/helpers.py)
# ---------------------------------------------------------------------------


def test_fake_read_bytes_returns_none_for_a_never_written_name():
    storage = FakeDeviceStorage()

    assert storage.read_bytes("state.json") is None


def test_fake_write_bytes_then_read_bytes_round_trips_exact_bytes():
    storage = FakeDeviceStorage()

    storage.write_bytes("state.json", b"\x00\x01hello\xff")

    assert storage.read_bytes("state.json") == b"\x00\x01hello\xff"


def test_fake_write_bytes_replaces_prior_content_entirely():
    storage = FakeDeviceStorage()
    storage.write_bytes("state.json", b"original-content")

    storage.write_bytes("state.json", b"new")

    assert storage.read_bytes("state.json") == b"new"


def test_fake_write_bytes_supports_subpaths_with_no_directory_setup():
    storage = FakeDeviceStorage()

    storage.write_bytes("scenes/tag/state.json", b"tag-state")

    assert storage.read_bytes("scenes/tag/state.json") == b"tag-state"


@pytest.mark.parametrize("escaping_name", ESCAPING_NAMES)
def test_fake_read_bytes_rejects_a_name_that_escapes_the_mount_root(escaping_name):
    storage = FakeDeviceStorage()

    with pytest.raises(ValueError):
        storage.read_bytes(escaping_name)


@pytest.mark.parametrize("escaping_name", ESCAPING_NAMES)
def test_fake_write_bytes_rejects_a_name_that_escapes_the_mount_root(escaping_name):
    storage = FakeDeviceStorage()

    with pytest.raises(ValueError):
        storage.write_bytes(escaping_name, b"data")


@pytest.mark.parametrize("escaping_subpath", ESCAPING_NAMES)
def test_fake_path_rejects_a_subpath_that_escapes_the_mount_root(escaping_subpath):
    storage = FakeDeviceStorage()

    with pytest.raises(ValueError):
        storage.path(escaping_subpath)


def test_fake_path_returns_a_resolved_path_under_the_fake_mount_root():
    storage = FakeDeviceStorage()

    assert storage.path("scenes/tag/state.json") == "/fake-mount/scenes/tag/state.json"


def test_fake_path_creates_no_entry_observable_via_read_bytes():
    storage = FakeDeviceStorage()

    storage.path("scenes/tag/state.json")

    assert storage.read_bytes("scenes/tag/state.json") is None


# ---------------------------------------------------------------------------
# FakeDeviceStorage — mount_root
# ---------------------------------------------------------------------------


def test_fake_mount_root_matches_the_root_path_prefixes():
    storage = FakeDeviceStorage()

    assert storage.mount_root == "/fake-mount"


def test_fake_mount_root_omits_the_trailing_slash_that_path_of_empty_string_includes():
    storage = FakeDeviceStorage()

    assert storage.mount_root == "/fake-mount"
    assert storage.path("") == "/fake-mount/"


# ---------------------------------------------------------------------------
# FakeDeviceStorage — read_json / write_json
# ---------------------------------------------------------------------------


def test_fake_read_json_returns_none_for_a_never_written_name():
    storage = FakeDeviceStorage()

    assert storage.read_json("state.json") is None


def test_fake_write_json_then_read_json_round_trips_a_mapping():
    storage = FakeDeviceStorage()

    storage.write_json("state.json", {"scene": "tag", "score": 3})

    assert storage.read_json("state.json") == {"scene": "tag", "score": 3}


def test_fake_read_json_raises_on_malformed_content():
    storage = FakeDeviceStorage()
    storage.write_bytes("state.json", b"{not valid json")

    with pytest.raises(json.JSONDecodeError):
        storage.read_json("state.json")


@pytest.mark.parametrize("escaping_name", ESCAPING_NAMES)
def test_fake_read_json_rejects_a_name_that_escapes_the_mount_root(escaping_name):
    storage = FakeDeviceStorage()

    with pytest.raises(ValueError):
        storage.read_json(escaping_name)


@pytest.mark.parametrize("escaping_name", ESCAPING_NAMES)
def test_fake_write_json_rejects_a_name_that_escapes_the_mount_root(escaping_name):
    storage = FakeDeviceStorage()

    with pytest.raises(ValueError):
        storage.write_json(escaping_name, {"scene": "tag"})

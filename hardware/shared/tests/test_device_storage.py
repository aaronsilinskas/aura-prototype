"""Behaviour-driven tests for the DeviceStorage port (hardware/shared/device_storage.py).

Covers:
- DeviceStorage: real-filesystem behaviour (tmp_path-backed) — none-on-missing,
  round-trip, atomic-replace-on-failure, subpath auto-create, escape rejection,
  path() resolution, mount_root accessor
- FakeDeviceStorage: the in-memory test double this file's own tests drive to
  prove it models the same observable contract
"""

import builtins
import errno
import os

import pytest

from hardware.shared.device_storage import DeviceStorage, reject_escaping_path

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

    real_open = builtins.open

    def flaky_open(path, mode="r", *args, **kwargs):
        if str(path).endswith(".tmp") and "w" in mode:
            raise OSError("simulated disk full")
        return real_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", flaky_open)

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


@pytest.mark.parametrize(
    "escaping_name",
    ["../secret.txt", "scenes/../../secret.txt", "/etc/passwd"],
)
def test_read_bytes_rejects_a_name_that_escapes_the_mount_root(tmp_path, escaping_name):
    storage = DeviceStorage(str(tmp_path))

    with pytest.raises(ValueError):
        storage.read_bytes(escaping_name)


@pytest.mark.parametrize(
    "escaping_name",
    ["../secret.txt", "scenes/../../secret.txt", "/etc/passwd"],
)
def test_write_bytes_rejects_a_name_that_escapes_the_mount_root(tmp_path, escaping_name):
    storage = DeviceStorage(str(tmp_path))

    with pytest.raises(ValueError):
        storage.write_bytes(escaping_name, b"data")


@pytest.mark.parametrize(
    "escaping_subpath",
    ["../secret.txt", "scenes/../../secret.txt", "/etc/passwd"],
)
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
# FakeDeviceStorage — in-memory test double
# ---------------------------------------------------------------------------


class FakeDeviceStorage:
    """In-memory ``DeviceStorage`` double modelling its observable contract.

    Not a subclass of :class:`DeviceStorage` — that class is a concrete,
    directly-instantiable filesystem adapter (there is no separate abstract
    port to share, unlike ``RadioTransport``/``PulseWriter``), so this fake
    reimplements the same accessor surface against a plain dict rather
    than inheriting filesystem behaviour it would only have to override.

    Models: ``None`` on a never-written name, atomic replace (a write only
    ever produces "prior content" or "new content", nothing torn), subpaths
    round-tripping with no directory bookkeeping required, and escape
    rejection identical to the real port's.
    """

    _MOUNT_ROOT = "/fake-mount"

    def __init__(self) -> None:
        self._files: dict[str, bytes] = {}

    @property
    def mount_root(self) -> str:
        return self._MOUNT_ROOT

    def read_bytes(self, name: str) -> "bytes | None":
        self._guard(name)
        return self._files.get(name)

    def write_bytes(self, name: str, data: bytes) -> None:
        self._guard(name)
        self._files[name] = bytes(data)

    def path(self, subpath: str) -> str:
        self._guard(subpath)
        return self._MOUNT_ROOT + "/" + subpath

    def _guard(self, relative_path: str) -> None:
        reject_escaping_path(relative_path)


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


@pytest.mark.parametrize(
    "escaping_name",
    ["../secret.txt", "scenes/../../secret.txt", "/etc/passwd"],
)
def test_fake_read_bytes_rejects_a_name_that_escapes_the_mount_root(escaping_name):
    storage = FakeDeviceStorage()

    with pytest.raises(ValueError):
        storage.read_bytes(escaping_name)


@pytest.mark.parametrize(
    "escaping_name",
    ["../secret.txt", "scenes/../../secret.txt", "/etc/passwd"],
)
def test_fake_write_bytes_rejects_a_name_that_escapes_the_mount_root(escaping_name):
    storage = FakeDeviceStorage()

    with pytest.raises(ValueError):
        storage.write_bytes(escaping_name, b"data")


@pytest.mark.parametrize(
    "escaping_subpath",
    ["../secret.txt", "scenes/../../secret.txt", "/etc/passwd"],
)
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

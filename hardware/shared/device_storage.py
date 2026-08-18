"""DeviceStorage — the board-free device-state storage port.

Reads and writes small device-state files under a mount root (e.g. an SD
card) and resolves real filesystem paths for streamed/scanned consumers
(audio ``open()``+``WaveFile``, scene ``os.listdir``). Every *name*/*subpath*
passed in routes through :meth:`DeviceStorage._resolve`, the one place that
joins it onto the mount root and rejects any attempt to escape it; the
``mount_root`` accessor is the one exception, since it reads the
already-owned root rather than resolving a caller-supplied path.

No ``board``/``busio``/CircuitPython-only import — safe on CPython,
CircuitPython 10.x, and MicroPython. Mounting the card is someone else's
job: the live adapter is ``hardware.circuitpython.sdcard_storage.SdCardStorage``,
which mounts at construction time and then defers every read/write to this
base class, since once mounted, plain ``os`` calls work identically across
runtimes. ``FakeDeviceStorage``, the in-memory test double, lives in
``hardware/shared/tests/test_device_storage.py`` (not shipped here),
mirroring where the board-free radio-transport fake lives.

Bytes primitives are the general seam; text/JSON convenience wrappers are
deferred to a later ticket.
"""

import errno
import os

try:
    from typing import Final
except ImportError:
    pass

__all__ = ["DeviceStorage", "reject_escaping_path"]

_TEMP_SUFFIX: Final = ".tmp"


def reject_escaping_path(relative_path: str) -> None:
    """Raise ``ValueError`` if *relative_path* escapes a mount root.

    Pure string logic shared by :meth:`DeviceStorage._resolve` and
    ``FakeDeviceStorage``'s guard so the escape-rejection rule can't drift
    between the real and fake implementations. Rejects an absolute
    *relative_path* (a leading ``"/"``) and any ``..`` path segment,
    wherever it appears, even one that would net out to a location still
    under the root — simple and conservatively safe rather than clever.
    """
    if relative_path.startswith("/"):
        raise ValueError(f"path escapes mount root: {relative_path!r}")
    for segment in relative_path.split("/"):
        if segment == "..":
            raise ValueError(f"path escapes mount root: {relative_path!r}")


class DeviceStorage:
    """Reads and writes device-state files under a mount root.

    Args:
        mount_root: Absolute filesystem path the card is mounted at (e.g.
            ``"/sd"``). Every *name*/*subpath* passed to the methods below is
            resolved relative to this root; trailing slashes are ignored.
    """

    def __init__(self, mount_root: str) -> None:
        self._mount_root = mount_root.rstrip("/") or "/"

    @property
    def mount_root(self) -> str:
        """The mount root with no trailing slash, e.g. for a ``sys.path`` entry.

        Unlike ``path("")``, which resolves through ``_resolve`` and so
        always carries the joining ``"/"``, this is the bare root string.
        """
        return self._mount_root

    def read_bytes(self, name: str) -> "bytes | None":
        """Return the full contents of *name*, or ``None`` if never written.

        A ``DeviceStorage`` instance always means "card mounted", so
        ``None`` unambiguously means "not written yet", never "no storage".

        Args:
            name: File name or subpath under the mount root.

        Raises:
            ValueError: *name* escapes the mount root (``..`` or an
                absolute path).
        """
        resolved = self._resolve(name)
        try:
            with open(resolved, "rb") as f:
                return f.read()
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise  # Anything but "not written yet" is a real failure.
            return None

    def write_bytes(self, name: str, data: bytes) -> None:
        """Durably, atomically-as-FAT-allows replace *name* with *data*.

        FAT ``os.rename`` raises ``EEXIST`` on an existing target, so true
        POSIX atomic replace is impossible. Instead: write a sibling temp
        file, ``os.sync()``, remove the existing target if present, then
        ``os.rename(temp, name)`` and ``os.sync()`` again — a reader opening
        *name* therefore only ever observes the complete old content or the
        complete new content, never a torn file. Missing parent directories
        are created by walking each segment with a single-level
        ``os.mkdir`` (there is no ``os.makedirs`` on CircuitPython),
        tolerating already-present directories.

        Args:
            name: File name or subpath under the mount root.
            data: Full contents to write.

        Raises:
            ValueError: *name* escapes the mount root (``..`` or an
                absolute path).
        """
        resolved = self._resolve(name)
        self._ensure_parent_dirs(name)

        temp_path = resolved + _TEMP_SUFFIX
        with open(temp_path, "wb") as f:
            f.write(data)
        os.sync()

        try:
            os.remove(resolved)
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise  # Anything but "nothing to replace" is a real failure.

        os.rename(temp_path, resolved)
        os.sync()

    def path(self, subpath: str) -> str:
        """Return *subpath* resolved to a real filesystem path under the mount root.

        A pure resolver — creates no directories. Intended for consumers
        that stream or scan a path themselves (audio ``open()``+
        ``WaveFile``, scene ``os.listdir``).

        Args:
            subpath: File or directory subpath under the mount root.

        Raises:
            ValueError: *subpath* escapes the mount root (``..`` or an
                absolute path).
        """
        return self._resolve(subpath)

    def _resolve(self, relative_path: str) -> str:
        """Join *relative_path* onto the mount root, rejecting any escape.

        Hand-rolled rather than built on the repo's ``engine._path.normpath``
        because that helper is identity on CircuitPython/MicroPython (no
        ``os.path`` to fall back to) and so does not collapse ``..`` there,
        even though it does on CPython — relying on it would make escape
        rejection platform-dependent. See :func:`reject_escaping_path` for
        the guard rule itself.
        """
        reject_escaping_path(relative_path)
        return self._mount_root + "/" + relative_path

    def _ensure_parent_dirs(self, relative_path: str) -> None:
        """Create every missing directory segment above *relative_path*'s file.

        Walks from the mount root down, ``os.mkdir``-ing one segment at a
        time and tolerating a segment that already exists — there is no
        ``os.makedirs`` on CircuitPython.
        """
        segments = relative_path.split("/")[:-1]
        current = self._mount_root
        for segment in segments:
            current = current + "/" + segment
            try:
                os.mkdir(current)
            except OSError as e:
                if e.errno != errno.EEXIST:
                    raise  # Anything but "already present" is a real failure.

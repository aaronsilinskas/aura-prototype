"""PackRegistry — auto-discovers named packs from a directory and lazily loads items."""

from __future__ import annotations

import os

try:
    from collections.abc import Callable
    from typing import TypeVar

    T = TypeVar("T")
except ImportError:
    pass


def _parse_version(version_str: str) -> tuple[int, int]:
    """Parse a ``'MAJOR.MINOR'`` string into an ``(major, minor)`` int tuple."""
    parts = version_str.strip().split(".")
    return int(parts[0]), int(parts[1])


class _PackEntry:
    """Metadata for a single discovered pack. Internal use only."""

    __slots__ = ("item_names", "module_prefix", "name", "source_path", "version_str")

    def __init__(
        self,
        name: str,
        version_str: str,
        module_prefix: str,
        item_names: set[str],
        source_path: str,
    ) -> None:
        self.name = name
        self.version_str = version_str
        self.module_prefix = module_prefix
        self.item_names = item_names
        self.source_path = source_path


class PackRegistry:
    """Auto-discovers named packs from a directory and lazily loads items.

    Construction::

        registry = PackRegistry(extractor=lambda module: module.BUILD)

    Scanning::

        registry.scan_dir("/path/to/packs", "packs.effects")

    Item access::

        builder = registry.get("elements", "fire")

    Version check::

        registry.check_version("elements", required_major=1, required_minor=2)
    """

    __slots__ = ("_cache", "_extractor", "_packs", "_scanned_dirs")

    def __init__(self, extractor: Callable[[object], T]) -> None:
        self._extractor = extractor
        self._packs: dict[str, _PackEntry] = {}
        self._cache: dict[tuple[str, str], object] = {}
        self._scanned_dirs: set[str] = set()

    def scan_dir(self, path: str, module_prefix: str) -> None:
        """Scan *path* for subdirectories that contain ``version.txt``.

        Each such subdirectory is registered as a pack.  The pack name is the
        directory name; the stored module prefix is
        ``module_prefix + "." + pack_name``; valid item names are all ``.py``
        files in that directory excluding ``__init__.py``.

        This method is idempotent: calling it a second time with the same
        *path* is a no-op.  Discovering a pack name that was already registered
        from a **different** source path raises ``ValueError``.
        """
        norm_path = os.path.normpath(path)
        if norm_path in self._scanned_dirs:
            return
        self._scanned_dirs.add(norm_path)

        for entry in os.listdir(norm_path):
            pack_dir = os.path.join(norm_path, entry)
            version_file = os.path.join(pack_dir, "version.txt")
            if not os.path.isdir(pack_dir) or not os.path.isfile(version_file):
                continue

            pack_name = entry

            if pack_name in self._packs:
                existing = self._packs[pack_name]
                if existing.source_path != norm_path:
                    raise ValueError(
                        "Pack '"
                        + pack_name
                        + "' already registered from '"
                        + existing.source_path
                        + "'; cannot register the same pack name from '"
                        + norm_path
                        + "'"
                    )
                continue

            with open(version_file) as fh:
                version_str = fh.readline().strip()

            item_names: set[str] = set()
            for fname in os.listdir(pack_dir):
                if fname.endswith(".py") and fname != "__init__.py":
                    item_names.add(fname[:-3])

            full_prefix = module_prefix + "." + pack_name
            self._packs[pack_name] = _PackEntry(
                name=pack_name,
                version_str=version_str,
                module_prefix=full_prefix,
                item_names=item_names,
                source_path=norm_path,
            )

    def get(self, pack_name: str, item_name: str) -> T:
        """Return the extracted value for *item_name* from *pack_name*.

        The item is imported on first access and the result is cached.

        Raises:
            ValueError: if *pack_name* is unknown.
            ValueError: if *item_name* is not in the recorded set for the pack
                (raised before any import attempt).
        """
        meta = self._packs.get(pack_name)
        if meta is None:
            raise ValueError("Unknown pack '" + pack_name + "'")

        if item_name not in meta.item_names:
            raise ValueError(
                "Unknown item '"
                + item_name
                + "' in pack '"
                + pack_name
                + "'. Available: "
                + ", ".join(sorted(meta.item_names))
            )

        cache_key = (pack_name, item_name)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]

        full_module = meta.module_prefix + "." + item_name
        module = __import__(full_module, fromlist=[""])
        value = self._extractor(module)
        self._cache[cache_key] = value
        return value  # type: ignore[return-value]

    def check_version(
        self, pack_name: str, required_major: int, required_minor: int
    ) -> None:
        """Verify that the installed pack version satisfies the minimum required.

        Compatibility rules (MAJOR.MINOR semantics):

        * Same major **and** installed minor >= required minor → compatible (no-op).
        * Same major **and** installed minor < required minor →
          ``ValueError`` containing "upgrade the pack".
        * Different major → ``ValueError`` containing "incompatible".

        Raises:
            ValueError: if *pack_name* is unknown.
            ValueError: if the installed version is not compatible.
        """
        meta = self._packs.get(pack_name)
        if meta is None:
            raise ValueError("Unknown pack '" + pack_name + "'")

        installed_major, installed_minor = _parse_version(meta.version_str)

        if installed_major != required_major:
            raise ValueError(
                "Pack '"
                + pack_name
                + "' version "
                + meta.version_str
                + " is incompatible with required "
                + str(required_major)
                + "."
                + str(required_minor)
            )

        if installed_minor < required_minor:
            raise ValueError(
                "Pack '"
                + pack_name
                + "' version "
                + meta.version_str
                + " is too old; upgrade the pack to at least "
                + str(required_major)
                + "."
                + str(required_minor)
            )

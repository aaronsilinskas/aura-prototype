"""PackRegistry — auto-discovers named packs from a directory and lazily loads items."""

import os

import engine._path as _path
from engine.version import Version

try:
    from typing import TypeVar

    T = TypeVar("T")
except ImportError:
    pass


class _PackEntry:
    """Metadata for a single discovered pack. Internal use only."""

    __slots__ = ("item_names", "module_prefix", "name", "source_path", "version")

    def __init__(
        self,
        name: str,
        version: Version,
        module_prefix: str,
        item_names: set[str],
        source_path: str,
    ) -> None:
        self.name = name
        self.version = version
        self.module_prefix = module_prefix
        self.item_names = item_names
        self.source_path = source_path


class PackRegistry:
    """Auto-discovers named packs from a directory and lazily loads items.

    Construction::

        registry = PackRegistry(item_attr="BUILD")

    Scanning::

        registry.scan_dir("/path/to/packs", "packs.effects")

    Item access::

        builder = registry.get("elements", "fire", EffectBuilder)

    Version check::

        registry.check_version("elements", Version(1, 2))
    """

    __slots__ = ("_cache", "_item_attr", "_packs", "_scanned_dirs")

    def __init__(self, item_attr: str) -> None:
        self._item_attr = item_attr
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
        norm_path = _path.normpath(path)
        if norm_path in self._scanned_dirs:
            return
        self._scanned_dirs.add(norm_path)

        for entry in os.listdir(norm_path):
            pack_dir = _path.join(norm_path, entry)
            version_file = _path.join(pack_dir, "version.txt")
            if not _path.isdir(pack_dir) or not _path.isfile(version_file):
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
                version=Version.parse(version_str),
                module_prefix=full_prefix,
                item_names=item_names,
                source_path=norm_path,
            )

    def get(self, pack_name: str, item_name: str, expected_class: "type[T]") -> "T":
        """Return the *item_attr* attribute of *item_name* from *pack_name*.

        The item is imported on first access and the result is cached.  On
        first load the value is verified with ``isinstance(value,
        expected_class)``; cache hits skip the check.

        Raises:
            ValueError: if *pack_name* is unknown.
            ValueError: if *item_name* is not in the recorded set for the pack
                (raised before any import attempt).
            ValueError: if the module has no attribute named *item_attr*.
            ValueError: if the attribute value is not an instance of
                *expected_class*.
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
        if cache_key in self._cache:
            return self._cache[cache_key]  # type: ignore[return-value]

        full_module = meta.module_prefix + "." + item_name
        module = __import__(full_module, None, None, [""])
        try:
            value = getattr(module, self._item_attr)
        except AttributeError:
            raise ValueError(
                "Pack '"
                + pack_name
                + "' item '"
                + item_name
                + "' has no attribute '"
                + self._item_attr
                + "'"
            ) from None
        if not isinstance(value, expected_class):
            raise ValueError(
                "Pack '"
                + pack_name
                + "' item '"
                + item_name
                + "' attribute '"
                + self._item_attr
                + "' is not an instance of "
                + expected_class.__name__
            )
        self._cache[cache_key] = value
        return value  # type: ignore[return-value]

    def items(self, pack_name: str) -> "list[str]":
        """Return item names for *pack_name* in alphabetical order.

        Raises:
            ValueError: if *pack_name* is unknown.
        """
        meta = self._packs.get(pack_name)
        if meta is None:
            raise ValueError("Unknown pack '" + pack_name + "'")
        return sorted(meta.item_names)

    def check_version(self, pack_name: str, required: Version) -> None:
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

        meta.version.check_compatible(pack_name, required.major, required.minor)

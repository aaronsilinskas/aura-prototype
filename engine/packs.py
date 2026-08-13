"""PackRegistry — auto-discovers named packs from a directory and lazily loads items."""

from __future__ import annotations

import os

import engine._path as _path
from engine.version import Version

try:
    from typing import TypeVar

    T = TypeVar("T")
except ImportError:
    pass


class RegistryError(ValueError):
    """Base class for typed registry lookup/load errors.

    Subclasses ``ValueError`` so existing ``except ValueError`` callers (rule
    loading, etc.) keep working unchanged.
    """


class UnknownPackError(RegistryError):
    """A ``pack_name`` has no registered pack.

    Raised by ``PackRegistry.get``, ``items``, and ``check_version``.
    """

    def __init__(self, pack_name: str) -> None:
        self.pack_name = pack_name
        super().__init__(f"Unknown pack '{pack_name}'")


class UnknownItemError(RegistryError):
    """An ``item_name`` is not registered.

    Shared by ``PackRegistry.get`` (where *pack_name* names the owning pack)
    and ``SceneLocalRegistry.get`` (where *pack_name* is ``None`` — scene-local
    items have no pack namespace).
    """

    def __init__(
        self,
        item_name: str,
        available: list[str],
        pack_name: str | None = None,
    ) -> None:
        self.item_name = item_name
        self.pack_name = pack_name
        self.available = available
        if pack_name is None:
            message = f"Unknown item '{item_name}'. Available: {', '.join(available)}"
        else:
            message = (
                f"Unknown item '{item_name}' in pack '{pack_name}'. "
                + f"Available: {', '.join(available)}"
            )
        super().__init__(message)


class MissingItemAttributeError(RegistryError):
    """A loaded item module has no attribute named *attr*.

    Raised by ``load_item``. *context* is the human-readable description of
    the owning registry entry (see ``load_item``).
    """

    def __init__(self, context: str, attr: str) -> None:
        self.context = context
        self.attr = attr
        super().__init__(f"{context} has no attribute '{attr}'")


class ItemTypeError(RegistryError):
    """A loaded item's attribute value is not an instance of *expected_class*.

    Raised by ``load_item``. *context* is the human-readable description of
    the owning registry entry (see ``load_item``).
    """

    def __init__(self, context: str, attr: str, expected_class: type) -> None:
        self.context = context
        self.attr = attr
        self.expected_class = expected_class
        super().__init__(
            f"{context} attribute '{attr}' is not an instance of {expected_class.__name__}"
        )


def scan_item_names(path: str) -> set[str]:
    """Return item names found in *path* under the canonical pack-item rule.

    Recognises ``.py`` and ``.mpy`` files; excludes ``__init__`` and directories.
    """
    names: set[str] = set()
    for fname in os.listdir(path):
        if fname.endswith(".mpy"):
            stem = fname[:-4]
        elif fname.endswith(".py"):
            stem = fname[:-3]
        else:
            continue
        if stem == "__init__":
            continue
        if _path.isdir(_path.join(path, fname)):
            continue
        names.add(stem)
    return names


def load_item(
    full_module: str,
    item_attr: str,
    context: str,
    expected_class: type[T],
) -> T:
    """Import *full_module*, extract *item_attr*, and verify it is an instance of
    *expected_class*.

    *context* is a human-readable description of the owning registry entry used
    in error messages (e.g. ``"Pack 'rlgl' item 'fire'"`` or
    ``"Scene 'forest' local item 'ambush'"``).  *full_module* is the dotted
    import path; *item_attr* is the attribute name to read from the module.

    Raises:
        MissingItemAttributeError: if the module has no attribute named *item_attr*.
        ItemTypeError: if the attribute value is not an instance of *expected_class*.
    """
    module = __import__(full_module, None, None, [""])
    try:
        value = getattr(module, item_attr)
    except AttributeError:
        raise MissingItemAttributeError(context, item_attr) from None
    if not isinstance(value, expected_class):
        raise ItemTypeError(context, item_attr, expected_class)
    return value  # type: ignore[return-value]


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

            if pack_name == "scene":
                raise ValueError(
                    "'scene' is a reserved system-wide name and cannot be used as a "
                    + f"pack name (found at '{pack_dir}')"
                )

            if pack_name in self._packs:
                existing = self._packs[pack_name]
                if existing.source_path != norm_path:
                    raise ValueError(
                        f"Pack '{pack_name}' already registered from "
                        + f"'{existing.source_path}'; cannot register the same pack name "
                        + f"from '{norm_path}'"
                    )
                continue

            with open(version_file) as fh:
                version_str = fh.readline().strip()

            item_names = scan_item_names(pack_dir)

            full_prefix = module_prefix + "." + pack_name
            self._packs[pack_name] = _PackEntry(
                name=pack_name,
                version=Version.parse(version_str),
                module_prefix=full_prefix,
                item_names=item_names,
                source_path=norm_path,
            )

    def names(self) -> list[str]:
        """Return all registered pack names alphabetically."""
        return sorted(self._packs)

    def get(self, pack_name: str, item_name: str, expected_class: type[T]) -> T:
        """Return the *item_attr* attribute of *item_name* from *pack_name*.

        The item is imported on first access and the result is cached.  On
        first load the value is verified with ``isinstance(value,
        expected_class)``; cache hits skip the check.

        Raises:
            UnknownPackError: if *pack_name* is unknown.
            UnknownItemError: if *item_name* is not in the recorded set for the
                pack (raised before any import attempt).
            MissingItemAttributeError: if the module has no attribute named
                *item_attr*.
            ItemTypeError: if the attribute value is not an instance of
                *expected_class*.
        """
        meta = self._packs.get(pack_name)
        if meta is None:
            raise UnknownPackError(pack_name)

        if item_name not in meta.item_names:
            raise UnknownItemError(item_name, sorted(meta.item_names), pack_name=pack_name)

        cache_key = (pack_name, item_name)
        if cache_key in self._cache:
            return self._cache[cache_key]  # type: ignore[return-value]

        full_module = meta.module_prefix + "." + item_name
        context = f"Pack '{pack_name}' item '{item_name}'"
        value = load_item(full_module, self._item_attr, context, expected_class)
        self._cache[cache_key] = value
        return value  # type: ignore[return-value]

    def items(self, pack_name: str) -> list[str]:
        """Return item names for *pack_name* in alphabetical order.

        Raises:
            UnknownPackError: if *pack_name* is unknown.
        """
        meta = self._packs.get(pack_name)
        if meta is None:
            raise UnknownPackError(pack_name)
        return sorted(meta.item_names)

    def check_version(self, pack_name: str, required: Version) -> None:
        """Verify that the installed pack version satisfies the minimum required.

        Delegates the MAJOR.MINOR compatibility check to
        :meth:`Version.check_compatible`.

        Raises:
            UnknownPackError: if *pack_name* is unknown.
            ValueError: if the installed version is not compatible.
        """
        meta = self._packs.get(pack_name)
        if meta is None:
            raise UnknownPackError(pack_name)

        meta.version.check_compatible(pack_name, required.major, required.minor)

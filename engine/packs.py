"""PackRegistry — named packs, filled by the pack catalog, whose items load lazily."""

from __future__ import annotations

import engine._path as _path
from engine.version import Version

try:
    from typing import TypeVar

    T = TypeVar("T")
except ImportError:
    pass


ITEM_EXTENSIONS = (".py", ".mpy")


class RegistryError(ValueError):
    """Base class for typed registry lookup/load errors.

    Subclasses ``ValueError`` so existing ``except ValueError`` callers (rule
    loading, etc.) keep working unchanged.
    """


class UnknownPackError(RegistryError):
    """A ``pack_name`` has no registered pack.

    Raised by ``PackRegistry.get`` and ``items``, and by the Active scene
    namespace, which also passes the qualified *name* it was resolving and its
    *kind* (``"effect"`` or ``"clip"``). Both stay ``None`` for a registry
    lookup, which keeps the plain wording.
    """

    def __init__(self, pack_name: str, name: str | None = None, kind: str | None = None) -> None:
        self.pack_name = pack_name
        self.name = name
        self.kind = kind
        if name is None or kind is None:
            message = f"Unknown pack '{pack_name}'"
        else:
            message = f"{kind.capitalize()} '{name}' uses unknown pack '{pack_name}'"
        super().__init__(message)


class UnknownItemError(RegistryError):
    """An ``item_name`` is not registered.

    Shared by ``PackRegistry.get`` (where *pack_name* names the owning pack)
    and ``SceneLocalRegistry.get`` (where *pack_name* is ``None`` — scene-local
    items have no pack namespace). The Active scene namespace also passes the
    qualified *name* it was resolving and its *kind* (``"effect"`` or
    ``"clip"``); both stay ``None`` for a registry lookup.
    """

    def __init__(
        self,
        item_name: str,
        available: list[str],
        pack_name: str | None = None,
        name: str | None = None,
        kind: str | None = None,
    ) -> None:
        self.item_name = item_name
        self.pack_name = pack_name
        self.available = available
        self.name = name
        self.kind = kind
        if name is not None and kind is not None:
            message = f"Unknown {kind} '{name}'. Available: {', '.join(available)}"
        elif pack_name is None:
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
    """Return item names found in *path*: its ``.py`` and ``.mpy`` stems.

    See ``engine._path.scan_stems`` for the stem rule.
    """
    return set(_path.scan_stems(path, ITEM_EXTENSIONS))


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
    ``"Local item 'ambush'"``).  *full_module* is the dotted
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
    """Named packs of one kind (effects or rules) whose items load lazily.

    Built only by ``engine.pack_catalog.scan_pack_roots``, which discovers the
    packs and sets the attribute their items export (``BUILD`` or ``RULE``).
    ``PackRegistry()`` is a valid empty registry.

    Item access::

        builder = catalog.effect_registry.get("elements", "fire", EffectBuilder)
    """

    __slots__ = ("_cache", "_item_attr", "_packs")

    def __init__(self) -> None:
        # Empty until ``_from_packs`` fills it and sets the export attribute;
        # until then every get() misses before reading it.
        self._item_attr: str | None = None
        self._packs: dict[str, _PackEntry] = {}
        self._cache: dict[tuple[str, str], object] = {}

    @staticmethod
    def _from_packs(item_attr: str, packs: list[_PackEntry]) -> PackRegistry:
        """Return a registry of *packs* whose items export *item_attr*.

        The ``PackCatalog`` construction path: the catalog has already scanned
        and validated every entry.
        """
        registry = PackRegistry()
        registry._item_attr = item_attr
        for entry in packs:
            registry._packs[entry.name] = entry
        return registry

    def names(self) -> list[str]:
        """Return all registered pack names alphabetically."""
        return sorted(self._packs)

    def get(self, pack_name: str, item_name: str, expected_class: type[T]) -> T:
        """Return the export (``BUILD`` or ``RULE``) of *item_name* from *pack_name*.

        The item is imported on first access and the result is cached.  On
        first load the value is verified with ``isinstance(value,
        expected_class)``; cache hits skip the check.

        Raises:
            UnknownPackError: if *pack_name* is unknown.
            UnknownItemError: if *item_name* is not in the recorded set for the
                pack (raised before any import attempt).
            MissingItemAttributeError: if the module lacks the export.
            ItemTypeError: if the export is not an instance of *expected_class*.
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

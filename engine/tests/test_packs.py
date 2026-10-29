"""Tests for engine.packs.PackRegistry lookups and the scan_item_names helper.

Registries come from ``scan_pack_roots`` over real trees laid out by the shared
``pack_tree`` builder, so lookups run the real ``__import__`` path. Discovery,
collision, reserved-name and version checks are catalog behaviour and live in
``test_pack_catalog.py``.
"""

from __future__ import annotations

import sys

import pytest

from engine.pack_catalog import scan_pack_roots
from engine.packs import (
    ItemTypeError,
    MissingItemAttributeError,
    PackRegistry,
    UnknownItemError,
    UnknownPackError,
    scan_item_names,
)


def _effect_registry(pack_tree, packs: dict[str, dict[str, str]]) -> PackRegistry:
    """Scan one root holding the given effect packs (pack name → item name → source)."""
    root = pack_tree.root("tp_flash")
    for pack_name, items in packs.items():
        pack_tree.effect_pack(root, pack_name, items=items)
    return scan_pack_roots([str(root)]).effect_registry


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_pack_registry_with_no_arguments_is_a_valid_empty_registry() -> None:
    registry = PackRegistry()

    assert registry.names() == []
    with pytest.raises(UnknownPackError) as excinfo:
        registry.get("anything", "item", object)
    assert excinfo.value.pack_name == "anything"


def test_pack_registry_does_not_allow_arbitrary_attributes() -> None:
    registry = PackRegistry()

    with pytest.raises(AttributeError):
        registry.unexpected_attr = "oops"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# get — item lookup validation
# ---------------------------------------------------------------------------


def test_get_raises_for_unknown_pack(pack_tree) -> None:
    registry = _effect_registry(pack_tree, {"mypack": {"item_a": "BUILD = 1"}})

    with pytest.raises(UnknownPackError) as excinfo:
        registry.get("nonexistent", "item_a", object)
    assert excinfo.value.pack_name == "nonexistent"


def test_get_raises_for_unknown_item_name_before_any_import(pack_tree) -> None:
    registry = _effect_registry(pack_tree, {"mypack": {"item_a": "BUILD = 1"}})
    known_before = set(sys.modules)

    with pytest.raises(UnknownItemError) as excinfo:
        registry.get("mypack", "ghost_item", object)
    assert excinfo.value.item_name == "ghost_item"
    assert excinfo.value.pack_name == "mypack"
    assert excinfo.value.available == ["item_a"]

    new_modules = set(sys.modules) - known_before
    assert new_modules == set(), f"Unexpected imports: {new_modules}"


def test_get_raises_unknown_item_for_init_py(pack_tree) -> None:
    registry = _effect_registry(pack_tree, {"mypack": {"__init__": "", "item_a": "BUILD = 7"}})

    with pytest.raises(UnknownItemError) as excinfo:
        registry.get("mypack", "__init__", object)
    assert excinfo.value.item_name == "__init__"


def test_get_returns_value_from_sibling_of_init_py(pack_tree) -> None:
    registry = _effect_registry(pack_tree, {"mypack": {"__init__": "", "item_a": "BUILD = 7"}})

    assert registry.get("mypack", "item_a", int) == 7


# ---------------------------------------------------------------------------
# get — lazy import + caching
# ---------------------------------------------------------------------------


def test_get_imports_module_and_returns_its_export_on_first_call(pack_tree) -> None:
    registry = _effect_registry(pack_tree, {"mypack": {"fire": "BUILD = 42"}})

    assert registry.get("mypack", "fire", int) == 42


def test_get_returns_cached_value_on_subsequent_calls(pack_tree) -> None:
    registry = _effect_registry(pack_tree, {"mypack": {"fire": "BUILD = object()"}})

    first = registry.get("mypack", "fire", object)
    second = registry.get("mypack", "fire", object)

    assert first is second


def test_get_only_imports_module_once(pack_tree) -> None:
    registry = _effect_registry(pack_tree, {"mypack": {"fire": "BUILD = 42"}})

    registry.get("mypack", "fire", int)
    modules_after_first = set(sys.modules)
    registry.get("mypack", "fire", int)

    assert set(sys.modules) == modules_after_first


# ---------------------------------------------------------------------------
# get — missing attribute / wrong type
# ---------------------------------------------------------------------------


def test_get_raises_missing_item_attribute_error_when_export_is_absent(pack_tree) -> None:
    registry = _effect_registry(pack_tree, {"mypack": {"item_a": "WRONG_NAME = 99"}})

    with pytest.raises(MissingItemAttributeError) as excinfo:
        registry.get("mypack", "item_a", object)
    assert excinfo.value.attr == "BUILD"
    assert excinfo.value.context == "Pack 'mypack' item 'item_a'"


def test_get_raises_item_type_error_when_export_has_wrong_type(pack_tree) -> None:
    registry = _effect_registry(pack_tree, {"mypack": {"item_a": "BUILD = 'not_an_int'"}})

    with pytest.raises(ItemTypeError) as excinfo:
        registry.get("mypack", "item_a", int)
    assert excinfo.value.attr == "BUILD"
    assert excinfo.value.expected_class is int
    assert excinfo.value.context == "Pack 'mypack' item 'item_a'"


# ---------------------------------------------------------------------------
# names — pack name listing
# ---------------------------------------------------------------------------


def test_names_returns_sorted_pack_names(pack_tree) -> None:
    registry = _effect_registry(pack_tree, {"zebra": {}, "alpha": {}, "mango": {}})

    assert registry.names() == ["alpha", "mango", "zebra"]


def test_names_returns_empty_list_when_no_packs_are_scanned(pack_tree) -> None:
    registry = _effect_registry(pack_tree, {})

    assert registry.names() == []


# ---------------------------------------------------------------------------
# items — item name listing
# ---------------------------------------------------------------------------


def test_items_returns_sorted_item_names(pack_tree) -> None:
    registry = _effect_registry(
        pack_tree, {"mypack": {"zebra": "BUILD = 1", "alpha": "BUILD = 2", "mango": "BUILD = 3"}}
    )

    assert registry.items("mypack") == ["alpha", "mango", "zebra"]


def test_items_returns_empty_list_for_pack_with_no_items(pack_tree) -> None:
    registry = _effect_registry(pack_tree, {"mypack": {}})

    assert registry.items("mypack") == []


def test_items_raises_for_unknown_pack(pack_tree) -> None:
    registry = _effect_registry(pack_tree, {})

    with pytest.raises(UnknownPackError) as excinfo:
        registry.items("nonexistent")
    assert excinfo.value.pack_name == "nonexistent"


# ---------------------------------------------------------------------------
# scan_item_names — public helper
# ---------------------------------------------------------------------------


def test_scan_item_names_returns_py_files_as_item_names(tmp_path) -> None:
    (tmp_path / "fire.py").write_text("")
    (tmp_path / "water.py").write_text("")

    result = scan_item_names(str(tmp_path))

    assert result == {"fire", "water"}


def test_scan_item_names_returns_mpy_files_as_item_names(tmp_path) -> None:
    (tmp_path / "fire.mpy").write_bytes(b"")
    (tmp_path / "water.mpy").write_bytes(b"")

    result = scan_item_names(str(tmp_path))

    assert result == {"fire", "water"}


def test_scan_item_names_deduplicates_py_and_mpy_with_same_stem(tmp_path) -> None:
    (tmp_path / "fire.py").write_text("")
    (tmp_path / "fire.mpy").write_bytes(b"")

    result = scan_item_names(str(tmp_path))

    assert result == {"fire"}


def test_scan_item_names_excludes_init_py(tmp_path) -> None:
    (tmp_path / "__init__.py").write_text("")
    (tmp_path / "item_a.py").write_text("")

    result = scan_item_names(str(tmp_path))

    assert result == {"item_a"}


def test_scan_item_names_excludes_init_mpy(tmp_path) -> None:
    (tmp_path / "__init__.mpy").write_bytes(b"")
    (tmp_path / "item_a.mpy").write_bytes(b"")

    result = scan_item_names(str(tmp_path))

    assert result == {"item_a"}


def test_scan_item_names_ignores_non_py_entries(tmp_path) -> None:
    (tmp_path / "subdir").mkdir()
    (tmp_path / "item_a.py").write_text("")

    result = scan_item_names(str(tmp_path))

    assert result == {"item_a"}


def test_scan_item_names_excludes_directory_whose_name_ends_in_py(tmp_path) -> None:
    fake = tmp_path / "looks_like.py"
    fake.mkdir()
    (tmp_path / "real_item.py").write_text("")

    result = scan_item_names(str(tmp_path))

    assert result == {"real_item"}


def test_scan_item_names_returns_empty_set_for_directory_with_no_py_files(
    tmp_path,
) -> None:
    (tmp_path / "version.txt").write_text("1.0\n")
    (tmp_path / "sounds").mkdir()

    result = scan_item_names(str(tmp_path))

    assert result == set()

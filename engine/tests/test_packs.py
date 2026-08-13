"""Tests for engine.packs.PackRegistry.

All tests use a real temporary filesystem (tmp_path) to exercise the actual
``os.listdir`` + ``__import__`` code path.
"""

from __future__ import annotations

import sys

import pytest

from engine.events import EffectEvent
from engine.packs import (
    ItemTypeError,
    MissingItemAttributeError,
    PackRegistry,
    UnknownItemError,
    UnknownPackError,
    scan_item_names,
)
from engine.version import Version

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


MODULE_PREFIX = "tp"


@pytest.fixture()
def pack_env(tmp_path):
    """Yield a ``tp/`` subdirectory of tmp_path as the packs root.

    ``tmp_path`` is inserted into ``sys.path`` so that module names of the
    form ``tp.<pack>.<item>`` resolve to the real files created by tests.
    All imported modules added during the test are removed on teardown.
    """
    packs_root = tmp_path / MODULE_PREFIX
    packs_root.mkdir()
    sys.path.insert(0, str(tmp_path))
    known_modules = set(sys.modules)
    yield packs_root
    # Remove any modules that were imported during the test.
    for key in list(sys.modules):
        if key not in known_modules:
            del sys.modules[key]
    sys.path.remove(str(tmp_path))


def _make_pack(root, pack_name: str, version: str, items: dict[str, str]) -> None:
    """Create a pack directory under *root* with the given version and item files."""
    pack_dir = root / pack_name
    pack_dir.mkdir(parents=True, exist_ok=True)
    (pack_dir / "version.txt").write_text(version + "\n")
    for item_name, content in items.items():
        (pack_dir / (item_name + ".py")).write_text(content)


def _make_registry(attr: str = "VALUE") -> PackRegistry:
    """Return a PackRegistry that reads the named module attribute."""
    return PackRegistry(item_attr=attr)


# ---------------------------------------------------------------------------
# scan_dir — discovery
# ---------------------------------------------------------------------------


def test_scan_dir_discovers_subdirectory_with_version_txt(pack_env) -> None:
    _make_pack(pack_env, "mypack", "1.0", {"item_a": "VALUE = 1"})
    registry = _make_registry()

    registry.scan_dir(str(pack_env), MODULE_PREFIX)

    assert registry.get("mypack", "item_a", int) == 1


def test_scan_dir_on_empty_directory_registers_no_packs(pack_env) -> None:
    registry = _make_registry()

    registry.scan_dir(str(pack_env), MODULE_PREFIX)

    with pytest.raises(UnknownPackError) as excinfo:
        registry.get("anything", "item", object)
    assert excinfo.value.pack_name == "anything"


def test_scan_dir_ignores_subdirectory_without_version_txt(pack_env) -> None:
    (pack_env / "notapack").mkdir()
    (pack_env / "notapack" / "item_a.py").write_text("VALUE = 99")
    registry = _make_registry()

    registry.scan_dir(str(pack_env), MODULE_PREFIX)

    with pytest.raises(UnknownPackError) as excinfo:
        registry.get("notapack", "item_a", object)
    assert excinfo.value.pack_name == "notapack"


def test_scan_dir_ignores_plain_files_at_top_level(pack_env) -> None:
    (pack_env / "readme.txt").write_text("hello")
    _make_pack(pack_env, "mypack", "1.0", {"item_a": "VALUE = 1"})
    registry = _make_registry()

    registry.scan_dir(str(pack_env), MODULE_PREFIX)

    assert registry.get("mypack", "item_a", int) == 1


def test_scan_dir_records_multiple_packs_from_same_directory(pack_env) -> None:
    _make_pack(pack_env, "pack_a", "1.0", {"x": "VALUE = 10"})
    _make_pack(pack_env, "pack_b", "2.0", {"y": "VALUE = 20"})
    registry = _make_registry()

    registry.scan_dir(str(pack_env), MODULE_PREFIX)

    assert registry.get("pack_a", "x", int) == 10
    assert registry.get("pack_b", "y", int) == 20


def test_scan_dir_no_modules_imported_during_scan(pack_env) -> None:
    _make_pack(pack_env, "mypack", "1.0", {"item_a": "VALUE = 1"})
    registry = _make_registry()
    known_before = set(sys.modules)

    registry.scan_dir(str(pack_env), MODULE_PREFIX)

    new_modules = set(sys.modules) - known_before
    assert new_modules == set(), f"Unexpected imports during scan: {new_modules}"


# ---------------------------------------------------------------------------
# scan_dir — idempotency
# ---------------------------------------------------------------------------


def test_scan_dir_called_twice_with_same_path_is_a_no_op(pack_env) -> None:
    _make_pack(pack_env, "mypack", "1.0", {"item_a": "VALUE = 1"})
    registry = _make_registry()

    registry.scan_dir(str(pack_env), MODULE_PREFIX)
    registry.scan_dir(str(pack_env), MODULE_PREFIX)

    assert registry.get("mypack", "item_a", int) == 1


def test_scan_dir_second_call_does_not_pick_up_packs_added_after_first_scan(
    pack_env,
) -> None:
    _make_pack(pack_env, "pack_a", "1.0", {"x": "VALUE = 1"})
    registry = _make_registry()
    registry.scan_dir(str(pack_env), MODULE_PREFIX)

    # Add a new pack after the first scan.
    _make_pack(pack_env, "pack_b", "1.0", {"y": "VALUE = 2"})
    registry.scan_dir(str(pack_env), MODULE_PREFIX)  # no-op

    with pytest.raises(ValueError, match="Unknown pack"):
        registry.get("pack_b", "y", object)


# ---------------------------------------------------------------------------
# scan_dir — name collision from different source
# ---------------------------------------------------------------------------


def test_scan_dir_raises_when_same_pack_name_comes_from_different_directory(
    pack_env,
) -> None:
    src_a = pack_env / "src_a"
    src_b = pack_env / "src_b"
    src_a.mkdir()
    src_b.mkdir()
    _make_pack(src_a, "mypack", "1.0", {"x": "VALUE = 1"})
    _make_pack(src_b, "mypack", "2.0", {"x": "VALUE = 2"})

    registry = _make_registry()
    registry.scan_dir(str(src_a), "tp.a")

    with pytest.raises(ValueError):
        registry.scan_dir(str(src_b), "tp.b")


# ---------------------------------------------------------------------------
# get — item lookup validation
# ---------------------------------------------------------------------------


def test_get_raises_for_unknown_pack(pack_env) -> None:
    registry = _make_registry()
    registry.scan_dir(str(pack_env), MODULE_PREFIX)

    with pytest.raises(UnknownPackError) as excinfo:
        registry.get("nonexistent", "item_a", object)
    assert excinfo.value.pack_name == "nonexistent"


def test_get_raises_for_unknown_item_name_before_any_import(pack_env) -> None:
    _make_pack(pack_env, "mypack", "1.0", {"item_a": "VALUE = 1"})
    registry = _make_registry()
    registry.scan_dir(str(pack_env), MODULE_PREFIX)
    known_before = set(sys.modules)

    with pytest.raises(UnknownItemError) as excinfo:
        registry.get("mypack", "ghost_item", object)
    assert excinfo.value.item_name == "ghost_item"
    assert excinfo.value.pack_name == "mypack"
    assert excinfo.value.available == ["item_a"]

    # No new modules should have been imported.
    new_modules = set(sys.modules) - known_before
    assert new_modules == set(), f"Unexpected imports: {new_modules}"


def test_get_excludes_init_py_from_valid_item_names(pack_env) -> None:
    pack_dir = pack_env / "mypack"
    pack_dir.mkdir()
    (pack_dir / "version.txt").write_text("1.0\n")
    (pack_dir / "__init__.py").write_text("")
    (pack_dir / "item_a.py").write_text("VALUE = 7")

    registry = _make_registry()
    registry.scan_dir(str(pack_env), MODULE_PREFIX)

    with pytest.raises(UnknownItemError) as excinfo:
        registry.get("mypack", "__init__", object)
    assert excinfo.value.item_name == "__init__"


def test_get_returns_value_from_sibling_of_init_py(pack_env) -> None:
    pack_dir = pack_env / "mypack"
    pack_dir.mkdir()
    (pack_dir / "version.txt").write_text("1.0\n")
    (pack_dir / "__init__.py").write_text("")
    (pack_dir / "item_a.py").write_text("VALUE = 7")

    registry = _make_registry()
    registry.scan_dir(str(pack_env), MODULE_PREFIX)

    assert registry.get("mypack", "item_a", int) == 7


# ---------------------------------------------------------------------------
# get — lazy import + caching
# ---------------------------------------------------------------------------


def test_get_imports_module_and_extracts_value_on_first_call(pack_env) -> None:
    _make_pack(pack_env, "mypack", "1.0", {"fire": "VALUE = 42"})
    registry = _make_registry()
    registry.scan_dir(str(pack_env), MODULE_PREFIX)

    result = registry.get("mypack", "fire", int)

    assert result == 42


def test_get_returns_cached_value_on_subsequent_calls(pack_env) -> None:
    _make_pack(pack_env, "mypack", "1.0", {"fire": "VALUE = 42"})
    registry = _make_registry()
    registry.scan_dir(str(pack_env), MODULE_PREFIX)

    first = registry.get("mypack", "fire", int)
    second = registry.get("mypack", "fire", int)

    assert first is second


def test_get_only_imports_module_once(pack_env) -> None:
    _make_pack(pack_env, "mypack", "1.0", {"fire": "VALUE = 42"})
    registry = _make_registry()
    registry.scan_dir(str(pack_env), MODULE_PREFIX)

    registry.get("mypack", "fire", int)
    modules_after_first = set(sys.modules)
    registry.get("mypack", "fire", int)

    assert set(sys.modules) == modules_after_first


def test_get_returns_named_attribute_value_from_pack_module(pack_env) -> None:
    _make_pack(pack_env, "mypack", "1.0", {"item_a": "GREETING = 'hello'"})
    registry = PackRegistry(item_attr="GREETING")
    registry.scan_dir(str(pack_env), MODULE_PREFIX)

    result = registry.get("mypack", "item_a", str)

    assert result == "hello"


# ---------------------------------------------------------------------------
# get — missing attribute / wrong type
# ---------------------------------------------------------------------------


def test_get_raises_value_error_when_attribute_is_missing_from_module(pack_env) -> None:
    _make_pack(pack_env, "mypack", "1.0", {"item_a": "WRONG_NAME = 99"})
    registry = PackRegistry(item_attr="VALUE")
    registry.scan_dir(str(pack_env), MODULE_PREFIX)

    with pytest.raises(MissingItemAttributeError) as excinfo:
        registry.get("mypack", "item_a", object)
    assert excinfo.value.attr == "VALUE"
    assert excinfo.value.context == "Pack 'mypack' item 'item_a'"


def test_get_raises_value_error_when_attribute_has_wrong_type(pack_env) -> None:
    _make_pack(pack_env, "mypack", "1.0", {"item_a": "VALUE = 'not_an_int'"})
    registry = PackRegistry(item_attr="VALUE")
    registry.scan_dir(str(pack_env), MODULE_PREFIX)

    with pytest.raises(ItemTypeError) as excinfo:
        registry.get("mypack", "item_a", int)
    assert excinfo.value.attr == "VALUE"
    assert excinfo.value.expected_class is int
    assert excinfo.value.context == "Pack 'mypack' item 'item_a'"


# ---------------------------------------------------------------------------
# check_version — compatible
# ---------------------------------------------------------------------------


def test_check_version_passes_when_installed_equals_required(pack_env) -> None:
    _make_pack(pack_env, "mypack", "1.2", {})
    registry = _make_registry()
    registry.scan_dir(str(pack_env), MODULE_PREFIX)

    registry.check_version("mypack", Version(1, 2))


def test_check_version_passes_when_installed_minor_is_greater(pack_env) -> None:
    _make_pack(pack_env, "mypack", "1.5", {})
    registry = _make_registry()
    registry.scan_dir(str(pack_env), MODULE_PREFIX)

    registry.check_version("mypack", Version(1, 2))


# ---------------------------------------------------------------------------
# check_version — minor too old
# ---------------------------------------------------------------------------


def test_check_version_raises_upgrade_message_when_installed_minor_is_less(
    pack_env,
) -> None:
    _make_pack(pack_env, "mypack", "1.1", {})
    registry = _make_registry()
    registry.scan_dir(str(pack_env), MODULE_PREFIX)

    with pytest.raises(ValueError, match="upgrade the pack"):
        registry.check_version("mypack", Version(1, 2))


# ---------------------------------------------------------------------------
# check_version — different major
# ---------------------------------------------------------------------------


def test_check_version_raises_incompatible_when_major_differs_higher(
    pack_env,
) -> None:
    _make_pack(pack_env, "mypack", "2.0", {})
    registry = _make_registry()
    registry.scan_dir(str(pack_env), MODULE_PREFIX)

    with pytest.raises(ValueError, match="incompatible"):
        registry.check_version("mypack", Version(1, 0))


def test_check_version_raises_incompatible_when_major_differs_lower(
    pack_env,
) -> None:
    _make_pack(pack_env, "mypack", "1.0", {})
    registry = _make_registry()
    registry.scan_dir(str(pack_env), MODULE_PREFIX)

    with pytest.raises(ValueError, match="incompatible"):
        registry.check_version("mypack", Version(2, 0))


def test_check_version_raises_for_unknown_pack(pack_env) -> None:
    registry = _make_registry()
    registry.scan_dir(str(pack_env), MODULE_PREFIX)

    with pytest.raises(UnknownPackError) as excinfo:
        registry.check_version("ghost", Version(1, 0))
    assert excinfo.value.pack_name == "ghost"


# ---------------------------------------------------------------------------
# PackRegistry uses __slots__
# ---------------------------------------------------------------------------


def test_pack_registry_uses_slots() -> None:
    assert hasattr(PackRegistry, "__slots__")


def test_pack_registry_does_not_allow_arbitrary_attributes() -> None:
    registry = _make_registry()

    with pytest.raises(AttributeError):
        registry.unexpected_attr = "oops"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# names — pack name listing
# ---------------------------------------------------------------------------


def test_names_returns_sorted_pack_names(pack_env) -> None:
    _make_pack(pack_env, "zebra", "1.0", {})
    _make_pack(pack_env, "alpha", "1.0", {})
    _make_pack(pack_env, "mango", "1.0", {})
    registry = _make_registry()
    registry.scan_dir(str(pack_env), MODULE_PREFIX)

    assert registry.names() == ["alpha", "mango", "zebra"]


def test_names_returns_empty_list_when_no_packs_registered(pack_env) -> None:
    registry = _make_registry()
    registry.scan_dir(str(pack_env), MODULE_PREFIX)

    assert registry.names() == []


# ---------------------------------------------------------------------------
# items — item name listing
# ---------------------------------------------------------------------------


def test_items_returns_sorted_item_names(pack_env) -> None:
    _make_pack(
        pack_env,
        "mypack",
        "1.0",
        {"zebra": "VALUE = 1", "alpha": "VALUE = 2", "mango": "VALUE = 3"},
    )
    registry = _make_registry()
    registry.scan_dir(str(pack_env), MODULE_PREFIX)

    assert registry.items("mypack") == ["alpha", "mango", "zebra"]


def test_items_returns_empty_list_for_pack_with_no_items(pack_env) -> None:
    _make_pack(pack_env, "mypack", "1.0", {})
    registry = _make_registry()
    registry.scan_dir(str(pack_env), MODULE_PREFIX)

    assert registry.items("mypack") == []


def test_items_excludes_init_py(pack_env) -> None:
    pack_dir = pack_env / "mypack"
    pack_dir.mkdir()
    (pack_dir / "version.txt").write_text("1.0\n")
    (pack_dir / "__init__.py").write_text("")
    (pack_dir / "item_a.py").write_text("VALUE = 1")

    registry = _make_registry()
    registry.scan_dir(str(pack_env), MODULE_PREFIX)

    assert registry.items("mypack") == ["item_a"]


def test_items_raises_for_unknown_pack(pack_env) -> None:
    registry = _make_registry()
    registry.scan_dir(str(pack_env), MODULE_PREFIX)

    with pytest.raises(UnknownPackError) as excinfo:
        registry.items("nonexistent")
    assert excinfo.value.pack_name == "nonexistent"


# ---------------------------------------------------------------------------
# sound_path — WAV file path resolution
# ---------------------------------------------------------------------------


def test_sound_path_returns_wav_path_for_registered_pack(pack_env) -> None:
    _make_pack(pack_env, "rlgl", "1.0", {})
    registry = _make_registry()
    registry.scan_dir(str(pack_env), MODULE_PREFIX)

    event = EffectEvent("rlgl", "red_light", "music")
    result = registry.sound_path(event)

    expected = str(pack_env / "rlgl") + "/sounds/red_light_music.wav"
    assert result == expected


def test_sound_path_returns_none_for_unknown_pack(pack_env) -> None:
    registry = _make_registry()
    registry.scan_dir(str(pack_env), MODULE_PREFIX)

    event = EffectEvent("nonexistent", "some", "sound")
    result = registry.sound_path(event)

    assert result is None


def test_sound_path_uses_pack_source_path(pack_env) -> None:
    src = pack_env / "custom_src"
    src.mkdir()
    _make_pack(src, "mygame", "1.0", {})
    registry = _make_registry()
    registry.scan_dir(str(src), MODULE_PREFIX)

    event = EffectEvent("mygame", "shield", "alert")
    result = registry.sound_path(event)

    assert result == str(src / "mygame") + "/sounds/shield_alert.wav"


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


# ---------------------------------------------------------------------------
# scan_dir — subdirectory named *.py is excluded from pack item names
# ---------------------------------------------------------------------------


def test_scan_dir_excludes_subdirectory_ending_in_py_from_item_names(pack_env) -> None:
    pack_dir = pack_env / "mypack"
    pack_dir.mkdir()
    (pack_dir / "version.txt").write_text("1.0\n")
    fake = pack_dir / "fake.py"
    fake.mkdir()
    (pack_dir / "real_item.py").write_text("VALUE = 1")

    registry = _make_registry()
    registry.scan_dir(str(pack_env), MODULE_PREFIX)

    assert registry.items("mypack") == ["real_item"]

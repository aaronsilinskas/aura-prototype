"""Tests for engine.pack_catalog.scan_pack_roots.

Every test lays out real pack roots with the shared ``pack_tree`` builder and
observes the result only through the returned catalog and its registries.
"""

from __future__ import annotations

import sys

import pytest

from engine.pack_catalog import (
    DuplicateNameError,
    IncompatiblePackError,
    MalformedSceneError,
    MalformedVersionError,
    MissingRootError,
    PackScanError,
    ReservedNameError,
    SceneDeclarationError,
    UnknownDeclaredPackError,
    scan_pack_roots,
)
from engine.packs import MissingItemAttributeError


def test_effect_packs_under_two_roots_load_their_build_export(pack_tree) -> None:
    flash = pack_tree.root("tc_flash")
    card = pack_tree.root("tc_card")
    pack_tree.effect_pack(flash, "basic", items={"glow": "BUILD = 1"})
    pack_tree.effect_pack(card, "extra", items={"spark": "BUILD = 2"})

    catalog = scan_pack_roots([str(flash), str(card)])

    assert catalog.effect_registry.names() == ["basic", "extra"]
    assert catalog.effect_registry.get("basic", "glow", int) == 1
    assert catalog.effect_registry.get("extra", "spark", int) == 2


def test_rule_packs_under_two_roots_load_their_rule_export(pack_tree) -> None:
    flash = pack_tree.root("tc_flash")
    card = pack_tree.root("tc_card")
    pack_tree.rule_pack(flash, "core", items={"tag": "RULE = 1"})
    pack_tree.rule_pack(card, "bonus", items={"ambush": "RULE = 2"})

    catalog = scan_pack_roots([str(flash), str(card)])

    assert catalog.rule_registry.names() == ["bonus", "core"]
    assert catalog.rule_registry.get("core", "tag", int) == 1
    assert catalog.rule_registry.get("bonus", "ambush", int) == 2


def test_a_rule_pack_item_exporting_only_build_is_missing_its_rule_attribute(pack_tree) -> None:
    root = pack_tree.root("tc_flash")
    pack_tree.rule_pack(root, "core", items={"tag": "BUILD = 1"})

    catalog = scan_pack_roots([str(root)])

    with pytest.raises(MissingItemAttributeError) as excinfo:
        catalog.rule_registry.get("core", "tag", int)
    assert excinfo.value.attr == "RULE"


def test_scenes_under_two_roots_are_all_registered(pack_tree) -> None:
    flash = pack_tree.root("tc_flash")
    card = pack_tree.root("tc_card")
    pack_tree.scene(flash, "lobby")
    pack_tree.scene(card, "forest")

    catalog = scan_pack_roots([str(flash), str(card)])

    assert catalog.scene_registry.names() == ["forest", "lobby"]


def test_a_card_scene_serves_its_local_rules(pack_tree) -> None:
    flash = pack_tree.root("tc_flash")
    card = pack_tree.root("tc_card")
    pack_tree.scene(card, "forest", rules={"greet": "RULE = 1"})

    forest = scan_pack_roots([str(flash), str(card)]).scene_registry.get("forest")

    assert forest.local_rule_registry.get("greet", int) == 1


def test_a_card_scene_serves_its_local_effects(pack_tree) -> None:
    flash = pack_tree.root("tc_flash")
    card = pack_tree.root("tc_card")
    pack_tree.scene(card, "forest", effects={"mist": "BUILD = 2"})

    forest = scan_pack_roots([str(flash), str(card)]).scene_registry.get("forest")

    assert forest.local_effect_registry.get("mist", int) == 2


def test_a_scene_maps_its_local_sounds_by_bare_stem(pack_tree) -> None:
    root = pack_tree.root("tc_flash")
    scene_dir = pack_tree.scene(root, "forest", sounds=["owl"])

    forest = scan_pack_roots([str(root)]).scene_registry.get("forest")

    assert forest.local_sound_map == {"owl": str(scene_dir / "sounds" / "owl.wav")}


def test_a_scene_without_a_sounds_folder_has_no_local_sounds(pack_tree) -> None:
    root = pack_tree.root("tc_flash")
    pack_tree.scene(root, "lobby")

    lobby = scan_pack_roots([str(root)]).scene_registry.get("lobby")

    assert lobby.local_sound_map == {}


def test_scanned_scene_carries_its_scene_json_fields(pack_tree) -> None:
    root = pack_tree.root("tc_flash")
    pack_tree.effect_pack(root, "basic")
    pack_tree.rule_pack(root, "core", version="1.2")
    pack_tree.scene(
        root,
        "tag",
        version="2.1",
        effect_packs=[["basic", "1.0"]],
        rule_packs=[["core", "1.2"]],
        ir_codec="nec",
        initial_data={"lives": 3},
    )

    scene = scan_pack_roots([str(root)]).scene_registry.get("tag")

    assert (scene.version.major, scene.version.minor) == (2, 1)
    assert scene.effect_packs == [["basic", "1.0"]]
    assert scene.rule_packs == [["core", "1.2"]]
    assert scene.ir_codec == "nec"
    assert scene.initial_data == {"lives": 3}


def test_scene_without_ir_codec_defaults_to_aura(pack_tree) -> None:
    root = pack_tree.root("tc_flash")
    pack_tree.scene(root, "tag")

    catalog = scan_pack_roots([str(root)])

    assert catalog.scene_registry.ir_codec_for("tag") == "aura"


def test_a_scene_local_rule_exporting_only_build_is_missing_its_rule_attribute(pack_tree) -> None:
    root = pack_tree.root("tc_flash")
    pack_tree.scene(root, "lobby", rules={"greet": "BUILD = 1"})

    lobby = scan_pack_roots([str(root)]).scene_registry.get("lobby")

    with pytest.raises(MissingItemAttributeError) as excinfo:
        lobby.local_rule_registry.get("greet", int)
    assert excinfo.value.attr == "RULE"


def test_pack_sounds_qualify_each_effect_pack_clip_with_its_pack_name(pack_tree) -> None:
    flash = pack_tree.root("tc_flash")
    card = pack_tree.root("tc_card")
    pack_tree.effect_pack(flash, "basic", sounds=["win"])
    pack_tree.effect_pack(card, "extra", sounds=["win", "lose"])

    catalog = scan_pack_roots([str(flash), str(card)])

    assert catalog.pack_sounds == {
        "basic.win": str(flash / "effects" / "basic" / "sounds" / "win.wav"),
        "extra.win": str(card / "effects" / "extra" / "sounds" / "win.wav"),
        "extra.lose": str(card / "effects" / "extra" / "sounds" / "lose.wav"),
    }


def _item_dir_and_lister(pack_tree, root, owner):
    """Return an item folder of *owner* (a pack, or a scene's rules or effects) and a
    lister of its scanned items."""
    if owner == "pack":
        item_dir = pack_tree.effect_pack(root, "basic", items={"glow": "BUILD = 1"})
        return item_dir, lambda catalog: catalog.effect_registry.items("basic")
    if owner == "scene_effects":
        scene_dir = pack_tree.scene(root, "lobby", effects={"glow": "BUILD = 1"})
        return scene_dir / "effects", lambda catalog: catalog.scene_registry.get(
            "lobby"
        ).local_effect_registry.items()
    scene_dir = pack_tree.scene(root, "lobby", rules={"glow": "RULE = 1"})
    return scene_dir / "rules", lambda catalog: catalog.scene_registry.get(
        "lobby"
    ).local_rule_registry.items()


@pytest.mark.parametrize("owner", ["pack", "scene_rules", "scene_effects"])
def test_mpy_item_files_count_like_py_files(pack_tree, owner) -> None:
    root = pack_tree.root("tc_flash")
    item_dir, scanned_items = _item_dir_and_lister(pack_tree, root, owner)
    (item_dir / "spark.mpy").write_bytes(b"")

    catalog = scan_pack_roots([str(root)])

    assert scanned_items(catalog) == ["glow", "spark"]


@pytest.mark.parametrize("owner", ["pack", "scene_rules", "scene_effects"])
def test_init_subdirectories_and_other_files_are_not_items(pack_tree, owner) -> None:
    root = pack_tree.root("tc_flash")
    item_dir, scanned_items = _item_dir_and_lister(pack_tree, root, owner)
    (item_dir / "__init__.py").write_text("")
    (item_dir / "helpers.py").mkdir()
    (item_dir / "tests").mkdir()
    (item_dir / "notes.txt").write_text("")

    catalog = scan_pack_roots([str(root)])

    assert scanned_items(catalog) == ["glow"]


def test_only_wav_files_count_as_pack_sounds(pack_tree) -> None:
    root = pack_tree.root("tc_flash")
    pack_dir = pack_tree.effect_pack(root, "basic", sounds=["win"])
    (pack_dir / "sounds" / "readme.txt").write_text("")

    catalog = scan_pack_roots([str(root)])

    assert list(catalog.pack_sounds) == ["basic.win"]


def test_only_wav_files_count_as_scene_sounds(pack_tree) -> None:
    root = pack_tree.root("tc_flash")
    scene_dir = pack_tree.scene(root, "lobby", sounds=["owl"])
    (scene_dir / "sounds" / "owl.mp3").write_bytes(b"")

    lobby = scan_pack_roots([str(root)]).scene_registry.get("lobby")

    assert list(lobby.local_sound_map) == ["owl"]


def test_a_directory_named_like_a_wav_is_not_a_pack_sound(pack_tree) -> None:
    root = pack_tree.root("tc_flash")
    pack_dir = pack_tree.effect_pack(root, "basic", sounds=["win"])
    (pack_dir / "sounds" / "fake.wav").mkdir()

    catalog = scan_pack_roots([str(root)])

    assert list(catalog.pack_sounds) == ["basic.win"]


def test_a_directory_named_like_a_wav_is_not_a_scene_sound(pack_tree) -> None:
    root = pack_tree.root("tc_flash")
    scene_dir = pack_tree.scene(root, "lobby", sounds=["owl"])
    (scene_dir / "sounds" / "fake.wav").mkdir()

    lobby = scan_pack_roots([str(root)]).scene_registry.get("lobby")

    assert list(lobby.local_sound_map) == ["owl"]


def test_an_effect_pack_without_a_sounds_folder_has_no_pack_sounds(pack_tree) -> None:
    root = pack_tree.root("tc_flash")
    pack_tree.effect_pack(root, "basic", items={"glow": "BUILD = 1"})

    catalog = scan_pack_roots([str(root)])

    assert catalog.pack_sounds == {}


def test_folders_without_a_marker_file_are_skipped(pack_tree) -> None:
    root = pack_tree.root("tc_flash")
    pack_tree.effect_pack(root, "helpers", version=None, items={"util": "BUILD = 1"})
    pack_tree.rule_pack(root, "leftover", version=None)
    (root / "scenes" / "drafts").mkdir(parents=True)
    (root / "effects" / "readme.txt").write_text("")

    catalog = scan_pack_roots([str(root)])

    assert catalog.effect_registry.names() == []
    assert catalog.rule_registry.names() == []
    assert catalog.scene_registry.names() == []


def test_a_root_with_no_kind_folders_scans_to_an_empty_catalog(pack_tree) -> None:
    root = pack_tree.root("tc_card")

    catalog = scan_pack_roots([str(root)])

    assert catalog.effect_registry.names() == []
    assert catalog.rule_registry.names() == []
    assert catalog.scene_registry.names() == []
    assert catalog.pack_sounds == {}


def test_a_missing_root_raises_missing_root_error(pack_tree, tmp_path) -> None:
    flash = pack_tree.root("tc_flash")
    missing = str(tmp_path / "nowhere" / "tc_card")

    with pytest.raises(MissingRootError) as excinfo:
        scan_pack_roots([str(flash), missing])

    assert excinfo.value.root == missing


def test_two_roots_with_the_same_folder_name_raise_duplicate_name_error(pack_tree) -> None:
    first = pack_tree.root("tc_flash", under="a")
    second = pack_tree.root("tc_flash", under="b")

    with pytest.raises(DuplicateNameError) as excinfo:
        scan_pack_roots([str(first), str(second)])

    assert (excinfo.value.name, excinfo.value.first_path, excinfo.value.second_path) == (
        "tc_flash",
        str(first),
        str(second),
    )


@pytest.mark.parametrize("kind", ["effect", "rule"])
def test_a_pack_name_under_two_roots_raises_duplicate_name_error(pack_tree, kind) -> None:
    flash = pack_tree.root("tc_flash")
    card = pack_tree.root("tc_card")
    make_pack = pack_tree.effect_pack if kind == "effect" else pack_tree.rule_pack
    first = make_pack(flash, "basic")
    second = make_pack(card, "basic")

    with pytest.raises(DuplicateNameError) as excinfo:
        scan_pack_roots([str(flash), str(card)])

    assert (excinfo.value.name, excinfo.value.first_path, excinfo.value.second_path) == (
        "basic",
        str(first),
        str(second),
    )


def test_a_scene_name_under_two_roots_raises_duplicate_name_error(pack_tree) -> None:
    flash = pack_tree.root("tc_flash")
    card = pack_tree.root("tc_card")
    first = pack_tree.scene(flash, "lobby")
    second = pack_tree.scene(card, "lobby")

    with pytest.raises(DuplicateNameError) as excinfo:
        scan_pack_roots([str(flash), str(card)])

    assert (excinfo.value.name, excinfo.value.first_path, excinfo.value.second_path) == (
        "lobby",
        str(first),
        str(second),
    )


def test_an_effect_pack_and_a_rule_pack_may_share_a_name(pack_tree) -> None:
    root = pack_tree.root("tc_flash")
    pack_tree.effect_pack(root, "tag")
    pack_tree.rule_pack(root, "tag")

    catalog = scan_pack_roots([str(root)])

    assert catalog.effect_registry.names() == ["tag"]
    assert catalog.rule_registry.names() == ["tag"]


@pytest.mark.parametrize("kind", ["effect", "rule"])
def test_a_pack_named_scene_raises_reserved_name_error(pack_tree, kind) -> None:
    root = pack_tree.root("tc_flash")
    make_pack = pack_tree.effect_pack if kind == "effect" else pack_tree.rule_pack
    pack_dir = make_pack(root, "scene")

    with pytest.raises(ReservedNameError) as excinfo:
        scan_pack_roots([str(root)])

    assert excinfo.value.path == str(pack_dir)


def test_every_scan_error_is_a_pack_scan_error_and_a_value_error() -> None:
    for error_type in (
        MissingRootError,
        DuplicateNameError,
        ReservedNameError,
        MalformedVersionError,
        MalformedSceneError,
    ):
        assert issubclass(error_type, PackScanError)
    assert issubclass(PackScanError, ValueError)


@pytest.mark.parametrize("kind", ["effect", "rule"])
def test_a_malformed_version_txt_raises_malformed_version_error_naming_the_file(
    pack_tree, kind
) -> None:
    root = pack_tree.root("tc_flash")
    make_pack = pack_tree.effect_pack if kind == "effect" else pack_tree.rule_pack
    pack_dir = make_pack(root, "basic", version="1")

    with pytest.raises(MalformedVersionError) as excinfo:
        scan_pack_roots([str(root)])

    assert excinfo.value.path == str(pack_dir / "version.txt")
    assert excinfo.value.value == "1"


@pytest.mark.parametrize("version", ["1", "one.two", 1.0])
def test_a_malformed_scene_version_raises_malformed_version_error_naming_scene_json(
    pack_tree, version
) -> None:
    root = pack_tree.root("tc_flash")
    scene_dir = pack_tree.scene(root, "lobby", version=version)

    with pytest.raises(MalformedVersionError) as excinfo:
        scan_pack_roots([str(root)])

    assert excinfo.value.path == str(scene_dir / "scene.json")
    assert excinfo.value.value == version


@pytest.mark.parametrize(
    "scene_json",
    [
        pytest.param("{not json", id="invalid-json"),
        pytest.param("[]", id="not-an-object"),
        pytest.param('{"effect_packs": [], "rule_packs": []}', id="missing-version"),
        pytest.param('{"version": "1.0", "rule_packs": []}', id="missing-effect-packs"),
        pytest.param('{"version": "1.0", "effect_packs": []}', id="missing-rule-packs"),
    ],
)
def test_an_unreadable_scene_json_raises_malformed_scene_error(pack_tree, scene_json) -> None:
    root = pack_tree.root("tc_flash")
    scene_dir = pack_tree.scene(root, "lobby", scene_json=scene_json)

    with pytest.raises(MalformedSceneError) as excinfo:
        scan_pack_roots([str(root)])

    assert excinfo.value.scene == "lobby"
    assert excinfo.value.path == str(scene_dir / "scene.json")


@pytest.mark.parametrize("ir_codec", ["", "   ", 7, None])
def test_a_malformed_ir_codec_raises_malformed_scene_error(pack_tree, ir_codec) -> None:
    root = pack_tree.root("tc_flash")
    scene_dir = pack_tree.scene(root, "lobby", ir_codec=ir_codec)

    with pytest.raises(MalformedSceneError) as excinfo:
        scan_pack_roots([str(root)])

    assert excinfo.value.scene == "lobby"
    assert excinfo.value.path == str(scene_dir / "scene.json")


def test_the_scan_stops_at_the_first_failure_in_root_order(pack_tree) -> None:
    flash = pack_tree.root("tc_flash")
    card = pack_tree.root("tc_card")
    flash_pack = pack_tree.effect_pack(flash, "basic", version="bad")
    pack_tree.effect_pack(card, "scene")

    with pytest.raises(MalformedVersionError) as excinfo:
        scan_pack_roots([str(flash), str(card)])

    assert excinfo.value.path == str(flash_pack / "version.txt")


def test_a_root_off_the_import_path_is_importable_after_the_scan(pack_tree, tmp_path) -> None:
    root = pack_tree.root("tc_card", under="sd")
    pack_tree.effect_pack(root, "extra", items={"spark": "BUILD = 2"})
    assert str(tmp_path / "sd") not in sys.path

    catalog = scan_pack_roots([str(root)])

    assert catalog.effect_registry.get("extra", "spark", int) == 2


def test_a_root_parent_already_on_the_import_path_is_not_added_again(pack_tree, tmp_path) -> None:
    root = pack_tree.root("tc_card", under="sd")
    sys.path.append(str(tmp_path / "sd"))

    scan_pack_roots([str(root)])
    scan_pack_roots([str(root)])

    assert sys.path.count(str(tmp_path / "sd")) == 1


# ---------------------------------------------------------------------------
# Scene declarations
# ---------------------------------------------------------------------------


def test_a_scene_declaring_a_missing_effect_pack_raises_unknown_declared_pack_error(
    pack_tree,
) -> None:
    root = pack_tree.root("tc_flash")
    pack_tree.scene(root, "lobby", effect_packs=[["basic", "1.0"]])

    with pytest.raises(UnknownDeclaredPackError) as excinfo:
        scan_pack_roots([str(root)])

    assert (excinfo.value.scene, excinfo.value.pack) == ("lobby", "basic")


def test_a_scene_declaring_a_missing_rule_pack_raises_unknown_declared_pack_error(
    pack_tree,
) -> None:
    root = pack_tree.root("tc_flash")
    pack_tree.scene(root, "lobby", rule_packs=[["core", "1.0"]])

    with pytest.raises(UnknownDeclaredPackError) as excinfo:
        scan_pack_roots([str(root)])

    assert (excinfo.value.scene, excinfo.value.pack) == ("lobby", "core")


def test_a_rule_pack_declared_as_an_effect_pack_raises_unknown_declared_pack_error(
    pack_tree,
) -> None:
    root = pack_tree.root("tc_flash")
    pack_tree.rule_pack(root, "core")
    pack_tree.scene(root, "lobby", effect_packs=[["core", "1.0"]])

    with pytest.raises(UnknownDeclaredPackError) as excinfo:
        scan_pack_roots([str(root)])

    assert (excinfo.value.scene, excinfo.value.pack, excinfo.value.kind) == (
        "lobby",
        "core",
        "effect",
    )


def test_a_flash_scene_may_declare_packs_installed_on_the_card(pack_tree) -> None:
    flash = pack_tree.root("tc_flash")
    card = pack_tree.root("tc_card")
    pack_tree.scene(flash, "lobby", effect_packs=[["extra", "1.0"]], rule_packs=[["bonus", "1.0"]])
    pack_tree.effect_pack(card, "extra")
    pack_tree.rule_pack(card, "bonus")

    catalog = scan_pack_roots([str(flash), str(card)])

    assert catalog.scene_registry.names() == ["lobby"]


@pytest.mark.parametrize("key", ["effect_packs", "rule_packs"])
@pytest.mark.parametrize(
    "declarations",
    [
        pytest.param({"basic": "1.0"}, id="not-a-list"),
        pytest.param(["basic"], id="bare-name"),
        pytest.param([["basic"]], id="missing-minimum"),
        pytest.param([["basic", "1.0", "extra"]], id="extra-field"),
        pytest.param([["basic", 1.0]], id="non-string-minimum"),
        pytest.param([[7, "1.0"]], id="non-string-name"),
    ],
)
def test_a_malformed_declaration_raises_malformed_scene_error(pack_tree, key, declarations) -> None:
    root = pack_tree.root("tc_flash")
    scene_dir = pack_tree.scene(root, "lobby", **{key: declarations})

    with pytest.raises(MalformedSceneError) as excinfo:
        scan_pack_roots([str(root)])

    assert excinfo.value.scene == "lobby"
    assert excinfo.value.path == str(scene_dir / "scene.json")


def _scene_declaring_pack(pack_tree, root, kind, *, installed, required):
    """Install *kind* pack ``basic`` at *installed*; return scene ``lobby`` requiring *required*."""
    make_pack = pack_tree.effect_pack if kind == "effect" else pack_tree.rule_pack
    make_pack(root, "basic", version=installed)
    return pack_tree.scene(root, "lobby", **{kind + "_packs": [["basic", required]]})


@pytest.mark.parametrize("kind", ["effect", "rule"])
def test_a_malformed_declared_minimum_raises_malformed_version_error_naming_scene_json(
    pack_tree, kind
) -> None:
    root = pack_tree.root("tc_flash")
    scene_dir = _scene_declaring_pack(pack_tree, root, kind, installed="1.0", required="1")

    with pytest.raises(MalformedVersionError) as excinfo:
        scan_pack_roots([str(root)])

    assert excinfo.value.path == str(scene_dir / "scene.json")
    assert excinfo.value.value == "1"


@pytest.mark.parametrize(
    ("installed", "required"),
    [
        pytest.param("2.0", "1.0", id="newer-major"),
        pytest.param("1.5", "2.0", id="older-major"),
        pytest.param("1.2", "1.3", id="older-minor"),
    ],
)
@pytest.mark.parametrize("kind", ["effect", "rule"])
def test_an_incompatible_installed_pack_raises_incompatible_pack_error(
    pack_tree, kind, installed, required
) -> None:
    root = pack_tree.root("tc_flash")
    _scene_declaring_pack(pack_tree, root, kind, installed=installed, required=required)

    with pytest.raises(IncompatiblePackError) as excinfo:
        scan_pack_roots([str(root)])

    error = excinfo.value
    assert (error.scene, error.pack, str(error.installed), str(error.required)) == (
        "lobby",
        "basic",
        installed,
        required,
    )


@pytest.mark.parametrize("installed", ["1.3", "1.7"])
def test_an_installed_pack_with_the_same_major_and_at_least_the_minor_is_compatible(
    pack_tree, installed
) -> None:
    root = pack_tree.root("tc_flash")
    pack_tree.effect_pack(root, "basic", version=installed)
    pack_tree.scene(root, "lobby", effect_packs=[["basic", "1.3"]])

    catalog = scan_pack_roots([str(root)])

    assert catalog.scene_registry.names() == ["lobby"]


def test_a_pack_declared_twice_in_one_scene_is_checked_per_entry(pack_tree) -> None:
    root = pack_tree.root("tc_flash")
    pack_tree.effect_pack(root, "basic", version="1.2")
    pack_tree.scene(root, "lobby", effect_packs=[["basic", "1.0"], ["basic", "1.4"]])

    with pytest.raises(IncompatiblePackError) as excinfo:
        scan_pack_roots([str(root)])

    assert str(excinfo.value.required) == "1.4"


@pytest.mark.parametrize(
    ("installed", "required"),
    [
        pytest.param(None, "1.0", id="unknown-pack"),
        pytest.param("2.0", "1.0", id="incompatible-pack"),
    ],
)
def test_a_declaration_failure_is_caught_as_a_scene_declaration_pack_scan_error(
    pack_tree, installed, required
) -> None:
    root = pack_tree.root("tc_flash")
    if installed is None:
        pack_tree.scene(root, "lobby", effect_packs=[["basic", required]])
    else:
        _scene_declaring_pack(pack_tree, root, "effect", installed=installed, required=required)

    with pytest.raises(PackScanError) as excinfo:
        scan_pack_roots([str(root)])

    assert isinstance(excinfo.value, SceneDeclarationError)
    assert (excinfo.value.scene, excinfo.value.pack) == ("lobby", "basic")


# ---------------------------------------------------------------------------
# Scan side effects
# ---------------------------------------------------------------------------


def test_the_scan_imports_no_item_module(pack_tree) -> None:
    root = pack_tree.root("tc_flash")
    pack_tree.effect_pack(root, "basic", items={"glow": "BUILD = 1"})
    pack_tree.rule_pack(root, "core", items={"tag": "RULE = 1"})
    pack_tree.scene(root, "lobby", effects={"mist": "BUILD = 2"}, rules={"greet": "RULE = 2"})
    known_before = set(sys.modules)

    scan_pack_roots([str(root)])

    assert set(sys.modules) - known_before == set()


# ---------------------------------------------------------------------------
# Initial-data overrides
# ---------------------------------------------------------------------------


def test_an_initial_data_override_replaces_only_the_keys_it_names(pack_tree) -> None:
    root = pack_tree.root("tc_flash")
    pack_tree.scene(root, "tag", initial_data={"rounds": 10, "lives": 3})

    catalog = scan_pack_roots([str(root)], initial_data_overrides={"tag": {"rounds": 2}})

    assert catalog.scene_registry.get("tag").initial_data == {"rounds": 2, "lives": 3}


def test_an_initial_data_override_applies_to_a_scene_without_initial_data(pack_tree) -> None:
    root = pack_tree.root("tc_flash")
    pack_tree.scene(root, "tag")

    catalog = scan_pack_roots([str(root)], initial_data_overrides={"tag": {"rounds": 2}})

    assert catalog.scene_registry.get("tag").initial_data == {"rounds": 2}


def test_an_initial_data_override_for_an_unscanned_scene_raises_a_plain_value_error(
    pack_tree,
) -> None:
    root = pack_tree.root("tc_flash")
    pack_tree.scene(root, "lobby")
    pack_tree.scene(root, "tag")

    with pytest.raises(ValueError, match=r"'forest'.*lobby, tag") as excinfo:
        scan_pack_roots([str(root)], initial_data_overrides={"forest": {"rounds": 2}})

    assert not isinstance(excinfo.value, PackScanError)


# ---------------------------------------------------------------------------
# Scene discovery
# ---------------------------------------------------------------------------


def test_a_plain_file_in_the_scenes_folder_is_not_a_scene(pack_tree) -> None:
    root = pack_tree.root("tc_flash")
    pack_tree.scene(root, "lobby")
    (root / "scenes" / "readme.txt").write_text("")

    catalog = scan_pack_roots([str(root)])

    assert catalog.scene_registry.names() == ["lobby"]


def test_an_empty_scenes_folder_scans_to_no_scenes(pack_tree) -> None:
    root = pack_tree.root("tc_flash")
    (root / "scenes").mkdir()

    catalog = scan_pack_roots([str(root)])

    assert catalog.scene_registry.names() == []

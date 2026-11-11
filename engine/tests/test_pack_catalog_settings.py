"""The ``PackCatalog`` scan checks Setting declarations and overrides, and resolves Settings.

Every test lays out real pack roots with the shared ``pack_tree`` builder and
observes the result through the scanned scene's Settings or the error raised.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.pack_catalog import (
    MalformedManifestError,
    MalformedSceneError,
    OverrideOfUndeclaredPackError,
    PackCatalog,
    PackScanError,
    SceneDeclarationError,
    SettingOverrideError,
)

HOLD = {"hold_seconds": {"type": "float", "default": 5.0, "description": "Seconds to hold."}}


def _scene_with_rule_pack(
    pack_tree, settings: object, reference_settings: dict | None = None
) -> Path:
    """Lay out rule pack ``exit`` declaring *settings*, and scene ``game`` declaring it."""
    root = pack_tree.root("ts_flash")
    pack_tree.rule_pack(root, "exit", settings=settings)
    reference: dict[str, object] = {"name": "exit", "version": "1.0"}
    if reference_settings is not None:
        reference["settings"] = reference_settings
    pack_tree.scene(root, "game", rule_packs=[reference])
    return root


def _exit_overrides(**values: object) -> dict:
    return {"game": {"rule_packs": {"exit": values}}}


def _hold(catalog: PackCatalog) -> object:
    return catalog.scene_registry.get("game").settings.get("exit", "hold_seconds")


def _fields(error: SettingOverrideError) -> tuple[str, str, str]:
    return error.scene, error.pack, error.setting


def test_a_pack_setting_resolves_to_its_declared_default(pack_tree) -> None:
    root = _scene_with_rule_pack(pack_tree, HOLD)

    assert _hold(pack_tree.scan_roots(root)) == 5.0


def test_a_scene_override_in_the_pack_reference_replaces_the_default(pack_tree) -> None:
    root = _scene_with_rule_pack(pack_tree, HOLD, {"hold_seconds": 2.5})

    assert _hold(pack_tree.scan_roots(root)) == 2.5


def test_a_scan_setting_override_replaces_the_scene_override(pack_tree) -> None:
    root = _scene_with_rule_pack(pack_tree, HOLD, {"hold_seconds": 2.5})

    catalog = pack_tree.scan_roots(root, setting_overrides=_exit_overrides(hold_seconds=0.5))

    assert _hold(catalog) == 0.5


def test_a_scan_setting_override_replaces_the_default_with_no_scene_override(pack_tree) -> None:
    root = _scene_with_rule_pack(pack_tree, HOLD)

    catalog = pack_tree.scan_roots(root, setting_overrides=_exit_overrides(hold_seconds=0.5))

    assert _hold(catalog) == 0.5


def test_a_scan_setting_override_leaves_other_scenes_at_their_own_values(pack_tree) -> None:
    root = _scene_with_rule_pack(pack_tree, HOLD)
    pack_tree.scene(root, "other", rule_packs=[{"name": "exit", "version": "1.0"}])

    catalog = pack_tree.scan_roots(root, setting_overrides=_exit_overrides(hold_seconds=0.5))

    assert catalog.scene_registry.get("other").settings.get("exit", "hold_seconds") == 5.0


@pytest.mark.parametrize(
    ("reference_settings", "setting_overrides"),
    [({"hold_seconds": 3}, None), (None, _exit_overrides(hold_seconds=3))],
    ids=["scene-override", "scan-override"],
)
def test_an_int_is_accepted_for_a_float_setting_and_resolves_as_a_float(
    pack_tree, reference_settings, setting_overrides
) -> None:
    root = _scene_with_rule_pack(pack_tree, HOLD, reference_settings)

    hold = _hold(pack_tree.scan_roots(root, setting_overrides=setting_overrides))

    assert hold == 3.0
    assert isinstance(hold, float)


def test_an_int_default_is_accepted_for_a_float_declaration(pack_tree) -> None:
    root = _scene_with_rule_pack(pack_tree, {"hold_seconds": {"type": "float", "default": 5}})

    hold = _hold(pack_tree.scan_roots(root))

    assert hold == 5.0
    assert isinstance(hold, float)


@pytest.mark.parametrize(
    ("type_name", "value"),
    [("int", 3), ("float", 0.5), ("bool", True), ("str", "red"), ("list", [1, "a", {"b": 2}])],
)
def test_each_type_resolves_a_value_of_that_type(pack_tree, type_name, value) -> None:
    root = _scene_with_rule_pack(
        pack_tree, {"hold_seconds": {"type": type_name}}, {"hold_seconds": value}
    )

    assert _hold(pack_tree.scan_roots(root)) == value


@pytest.mark.parametrize(
    ("reference_settings", "setting_overrides"),
    [({"hold_seconds": 1.0}, None), (None, _exit_overrides(hold_seconds=1.0))],
    ids=["scene-override", "scan-override"],
)
def test_a_required_setting_resolves_once_an_override_sets_it(
    pack_tree, reference_settings, setting_overrides
) -> None:
    root = _scene_with_rule_pack(pack_tree, {"hold_seconds": {"type": "float"}}, reference_settings)

    assert _hold(pack_tree.scan_roots(root, setting_overrides=setting_overrides)) == 1.0


def test_a_required_setting_left_unset_raises_setting_override_error(pack_tree) -> None:
    root = _scene_with_rule_pack(pack_tree, {"hold_seconds": {"type": "float"}})

    with pytest.raises(SettingOverrideError) as excinfo:
        pack_tree.scan_roots(root)

    assert _fields(excinfo.value) == ("game", "exit", "hold_seconds")


@pytest.mark.parametrize(
    ("reference_settings", "setting_overrides", "setting"),
    [
        ({"hold_secs": 2.0}, None, "hold_secs"),
        ({"hold_seconds": "long"}, None, "hold_seconds"),
        ({"hold_seconds": True}, None, "hold_seconds"),
        (None, _exit_overrides(hold_secs=2.0), "hold_secs"),
        (None, _exit_overrides(hold_seconds="long"), "hold_seconds"),
    ],
    ids=[
        "scene-unknown",
        "scene-wrong-type",
        "scene-bool-for-float",
        "scan-unknown",
        "scan-wrong-type",
    ],
)
def test_a_bad_override_raises_setting_override_error_naming_it(
    pack_tree, reference_settings, setting_overrides, setting
) -> None:
    root = _scene_with_rule_pack(pack_tree, HOLD, reference_settings)

    with pytest.raises(SettingOverrideError) as excinfo:
        pack_tree.scan_roots(root, setting_overrides=setting_overrides)

    assert _fields(excinfo.value) == ("game", "exit", setting)


@pytest.mark.parametrize(
    ("reference_settings", "setting_overrides"),
    [({"hold_seconds": {"a": 1}}, None), (None, _exit_overrides(hold_seconds="1, 2"))],
    ids=["scene-override", "scan-override"],
)
def test_a_non_list_value_for_a_list_setting_raises_setting_override_error(
    pack_tree, reference_settings, setting_overrides
) -> None:
    root = _scene_with_rule_pack(
        pack_tree, {"hold_seconds": {"type": "list", "default": []}}, reference_settings
    )

    with pytest.raises(SettingOverrideError) as excinfo:
        pack_tree.scan_roots(root, setting_overrides=setting_overrides)

    assert _fields(excinfo.value) == ("game", "exit", "hold_seconds")


def test_a_list_setting_is_checked_at_the_top_level_only(pack_tree) -> None:
    root = _scene_with_rule_pack(
        pack_tree, {"hold_seconds": {"type": "list"}}, {"hold_seconds": [None, [[]], "x"]}
    )

    assert _hold(pack_tree.scan_roots(root)) == [None, [[]], "x"]


def test_changing_a_resolved_list_setting_does_not_change_the_next_read(pack_tree) -> None:
    root = _scene_with_rule_pack(pack_tree, {"hold_seconds": {"type": "list", "default": [1]}})
    settings = pack_tree.scan_roots(root).scene_registry.get("game").settings

    settings.get("exit", "hold_seconds").append(2)  # type: ignore[union-attr]

    assert settings.get("exit", "hold_seconds") == [1]


@pytest.mark.parametrize(
    ("kind", "values"),
    [
        ("rule", {"hold_seconds": 1.0}),
        ("rule", {}),
        ("effect", {"hold_seconds": 1.0}),
        ("effect", {}),
    ],
    ids=[
        "rule-pack-with-values",
        "rule-pack-empty",
        "effect-pack-with-values",
        "effect-pack-empty",
    ],
)
def test_a_scan_override_for_a_pack_the_scene_does_not_declare_raises(
    pack_tree, kind: str, values: dict
) -> None:
    root = _scene_with_rule_pack(pack_tree, HOLD)
    getattr(pack_tree, kind + "_pack")(root, "unused", settings=HOLD)

    with pytest.raises(OverrideOfUndeclaredPackError) as excinfo:
        pack_tree.scan_roots(
            root, setting_overrides={"game": {kind + "_packs": {"unused": values}}}
        )

    error = excinfo.value
    assert (error.scene, error.pack, error.kind) == ("game", "unused", kind)


def test_a_scan_override_of_an_undeclared_scene_setting_raises(pack_tree) -> None:
    root = _scene_with_rule_pack(pack_tree, HOLD)

    with pytest.raises(SettingOverrideError) as excinfo:
        pack_tree.scan_roots(root, setting_overrides={"game": {"settings": {"max_ammo": 3}}})

    assert _fields(excinfo.value) == ("game", "scene", "max_ammo")


def test_a_scan_override_of_an_effect_pack_setting_is_checked_against_its_manifest(
    pack_tree,
) -> None:
    root = pack_tree.root("ts_flash")
    pack_tree.effect_pack(root, "glow", settings={"speed": {"type": "int", "default": 1}})
    pack_tree.scene(root, "game", effect_packs=[{"name": "glow", "version": "1.0"}])

    with pytest.raises(SettingOverrideError) as excinfo:
        pack_tree.scan_roots(
            root, setting_overrides={"game": {"effect_packs": {"glow": {"speed": 0.5}}}}
        )

    assert _fields(excinfo.value) == ("game", "glow", "speed")


def test_settings_on_an_effect_pack_reference_raise_malformed_scene_error(pack_tree) -> None:
    root = pack_tree.root("ts_flash")
    pack_tree.effect_pack(root, "glow")
    pack_tree.scene(root, "game", effect_packs=[{"name": "glow", "version": "1.0", "settings": {}}])

    with pytest.raises(MalformedSceneError) as excinfo:
        pack_tree.scan_roots(root)

    assert (excinfo.value.scene, excinfo.value.path) == (
        "game",
        str(root / "scenes" / "game" / "scene.json"),
    )


def test_a_setting_override_error_is_a_scene_declaration_error() -> None:
    assert issubclass(SettingOverrideError, SceneDeclarationError)


@pytest.mark.parametrize(
    "settings",
    [
        {"hold_seconds": {"type": "duration", "default": 5.0}},
        {"hold_seconds": {"default": 5.0}},
        {"hold_seconds": {"type": "float", "default": "5"}},
        {"hold_seconds": {"type": "int", "default": 5.5}},
        {"hold_seconds": {"type": "int", "default": True}},
        {"hold_seconds": {"type": "list", "default": "a, b"}},
        {"hold_seconds": {"type": "bool", "default": 0}},
        {"hold_seconds": {"type": "float", "defualt": 5.0}},
        {"hold_seconds": {"type": "float", "description": 5}},
        {"hold_seconds": 5.0},
        ["hold_seconds"],
    ],
    ids=[
        "unknown-type",
        "no-type",
        "str-default-for-float",
        "float-default-for-int",
        "bool-default-for-int",
        "str-default-for-list",
        "int-default-for-bool",
        "unknown-key",
        "non-str-description",
        "declaration-not-an-object",
        "section-not-an-object",
    ],
)
@pytest.mark.parametrize("kind", ["effect", "rule"])
def test_a_bad_declaration_raises_malformed_manifest_error_naming_the_manifest(
    pack_tree, kind, settings
) -> None:
    root = pack_tree.root("ts_flash")
    pack_dir = getattr(pack_tree, kind + "_pack")(root, "exit", settings=settings)

    with pytest.raises(MalformedManifestError) as excinfo:
        pack_tree.scan_roots(root)

    assert excinfo.value.path == str(pack_dir / (kind + "s.json"))


@pytest.mark.parametrize(
    "setting_overrides",
    [
        {"gmae": {}},
        {"game": {"rule_pack": {}}},
        {"game": {"rule_packs": {"exit": 1.0}}},
        {"game": {"settings": ["max_ammo"]}},
    ],
    ids=["unknown-scene", "unknown-key", "pack-not-a-dict", "settings-not-a-dict"],
)
def test_misshapen_setting_overrides_raise_a_plain_value_error(
    pack_tree, setting_overrides
) -> None:
    root = _scene_with_rule_pack(pack_tree, HOLD)

    with pytest.raises(ValueError) as excinfo:
        pack_tree.scan_roots(root, setting_overrides=setting_overrides)

    assert not isinstance(excinfo.value, PackScanError)


AMMO = {"max_ammo": {"type": "int", "default": 6, "description": "Shots per reload."}}


def _scene_declaring(pack_tree, settings: object) -> Path:
    """Lay out scene ``game`` declaring its own *settings* in ``scene.json``."""
    root = pack_tree.root("ts_flash")
    pack_tree.scene(root, "game", settings=settings)
    return root


def _max_ammo(catalog: PackCatalog) -> object:
    return catalog.scene_registry.get("game").settings.get("scene", "max_ammo")


def test_a_scene_setting_resolves_to_its_declared_default(pack_tree) -> None:
    root = _scene_declaring(pack_tree, AMMO)

    assert _max_ammo(pack_tree.scan_roots(root)) == 6


def test_a_scan_setting_override_replaces_a_scene_setting_default(pack_tree) -> None:
    root = _scene_declaring(pack_tree, AMMO)

    catalog = pack_tree.scan_roots(root, setting_overrides={"game": {"settings": {"max_ammo": 3}}})

    assert _max_ammo(catalog) == 3


@pytest.mark.parametrize(
    "settings",
    [
        {"max_ammo": {"type": "int"}},
        {"max_ammo": {"type": "int"}, "speed": {"type": "float", "default": 1.0}},
    ],
    ids=["only-setting", "beside-a-defaulted-one"],
)
def test_a_required_scene_setting_left_unset_raises_naming_the_scene_namespace(
    pack_tree, settings
) -> None:
    root = _scene_declaring(pack_tree, settings)

    with pytest.raises(SettingOverrideError) as excinfo:
        pack_tree.scan_roots(root)

    assert _fields(excinfo.value) == ("game", "scene", "max_ammo")


def test_a_scan_override_of_a_scene_setting_with_the_wrong_type_raises(pack_tree) -> None:
    root = _scene_declaring(pack_tree, AMMO)

    with pytest.raises(SettingOverrideError) as excinfo:
        pack_tree.scan_roots(root, setting_overrides={"game": {"settings": {"max_ammo": "3"}}})

    assert _fields(excinfo.value) == ("game", "scene", "max_ammo")


@pytest.mark.parametrize(
    "settings",
    [
        {"max_ammo": {"type": "ammo", "default": 6}},
        {"max_ammo": {"type": "int", "default": 6.5}},
        {"max_ammo": {"type": "int", "deafult": 6}},
        ["max_ammo"],
    ],
    ids=["unknown-type", "default-of-wrong-type", "unknown-key", "section-not-an-object"],
)
def test_a_bad_scene_declaration_raises_malformed_scene_error_naming_scene_json(
    pack_tree, settings
) -> None:
    root = _scene_declaring(pack_tree, settings)

    with pytest.raises(MalformedSceneError) as excinfo:
        pack_tree.scan_roots(root)

    assert (excinfo.value.scene, excinfo.value.path) == (
        "game",
        str(root / "scenes" / "game" / "scene.json"),
    )

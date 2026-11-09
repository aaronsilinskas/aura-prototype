"""Tests for scene and Rule pack ``requires`` declarations and the Capability errors.

Declarations are laid out on disk with the shared ``pack_tree`` builder and
observed through the scanned catalog's ``SceneRegistry``.
"""

from __future__ import annotations

import pytest

from engine.capabilities import MissingCapabilityError, UnknownCapabilityError
from engine.pack_catalog import MalformedManifestError, MalformedSceneError, PackScanError
from engine.scene import Scene, SceneRegistry

# ---------------------------------------------------------------------------
# Required capabilities
# ---------------------------------------------------------------------------


def test_a_scene_requires_the_capabilities_its_scene_json_lists(pack_tree) -> None:
    catalog = pack_tree.scan(scenes={"tag": {"requires": ["ir.line", "button.A"]}})

    assert catalog.scene_registry.required_capabilities("tag") == {"ir.line", "button.A"}


def test_a_scene_without_requires_requires_nothing(pack_tree) -> None:
    catalog = pack_tree.scan(scenes={"lobby": {}})

    assert catalog.scene_registry.required_capabilities("lobby") == frozenset()


def test_a_scene_requires_the_capabilities_of_every_rule_pack_it_declares(pack_tree) -> None:
    root = pack_tree.root("tc_flash")
    pack_tree.rule_pack(root, "return_to_lobby", requires=["button.A", "button.B", "storage"])
    pack_tree.rule_pack(root, "radar", requires=["radio"])
    pack_tree.rule_pack(root, "debug")
    pack_tree.scene(
        root,
        "tag",
        requires=["ir.line", "button.A"],
        rule_packs=[
            {"name": "return_to_lobby", "version": "1.0"},
            {"name": "radar", "version": "1.0"},
            {"name": "debug", "version": "1.0"},
        ],
    )

    catalog = pack_tree.scan_roots(root)

    assert catalog.scene_registry.required_capabilities("tag") == {
        "ir.line",
        "button.A",
        "button.B",
        "storage",
        "radio",
    }


def test_a_rule_pack_requirement_reaches_only_scenes_declaring_that_pack(pack_tree) -> None:
    root = pack_tree.root("tc_flash")
    pack_tree.rule_pack(root, "radar", requires=["radio"])
    pack_tree.scene(root, "with_radar", rule_packs=[{"name": "radar", "version": "1.0"}])
    pack_tree.scene(root, "without_radar")

    catalog = pack_tree.scan_roots(root)

    assert catalog.scene_registry.required_capabilities("without_radar") == frozenset()


def test_a_capability_listed_twice_is_required_once(pack_tree) -> None:
    catalog = pack_tree.scan(scenes={"tag": {"requires": ["radio", "radio"]}})

    assert catalog.scene_registry.required_capabilities("tag") == {"radio"}


@pytest.mark.parametrize(
    "name",
    [
        "button.A",
        "button.Z",
        "ir.line",
        "ir.cone",
        "ir.area_of_effect",
        "ir.receive",
        "radio",
        "storage",
        "accelerometer",
        "magnetometer",
    ],
)
def test_every_name_in_the_vocabulary_may_be_required(pack_tree, name) -> None:
    catalog = pack_tree.scan(scenes={"tag": {"requires": [name]}})

    assert catalog.scene_registry.required_capabilities("tag") == {name}


def test_a_scene_registered_in_memory_requires_nothing() -> None:
    registry = SceneRegistry()
    registry.register("probe", lambda: Scene(effect_packs=[], rule_packs=[]))

    assert registry.required_capabilities("probe") == frozenset()


def test_a_scene_registered_in_memory_over_a_scanned_one_requires_nothing(pack_tree) -> None:
    registry = pack_tree.scan(scenes={"tag": {"requires": ["radio"]}}).scene_registry
    registry.register("tag", lambda: Scene(effect_packs=[], rule_packs=[]))

    assert registry.required_capabilities("tag") == frozenset()


def test_required_capabilities_of_an_unregistered_scene_raises_value_error() -> None:
    with pytest.raises(ValueError):
        SceneRegistry().required_capabilities("nowhere")


# ---------------------------------------------------------------------------
# Scan failures
# ---------------------------------------------------------------------------

_UNKNOWN_NAMES = [
    pytest.param("pixels", id="not-a-capability"),
    pytest.param("button", id="button-without-label"),
    pytest.param("button.a", id="lowercase-button-label"),
    pytest.param("button.AB", id="two-letter-button-label"),
    pytest.param("ir", id="ir-without-emitter"),
    pytest.param("i2c.accelerometer", id="names-a-bus"),
    pytest.param(3, id="not-a-string"),
]


@pytest.mark.parametrize("name", _UNKNOWN_NAMES)
def test_a_scene_requiring_an_unknown_name_raises_unknown_capability_error(pack_tree, name) -> None:
    root = pack_tree.root("tc_flash")
    scene_dir = pack_tree.scene(root, "tag", requires=["radio", name])

    with pytest.raises(UnknownCapabilityError) as excinfo:
        pack_tree.scan_roots(root)

    assert (excinfo.value.path, excinfo.value.name) == (str(scene_dir / "scene.json"), name)


@pytest.mark.parametrize("name", _UNKNOWN_NAMES)
def test_a_rule_pack_requiring_an_unknown_name_raises_unknown_capability_error(
    pack_tree, name
) -> None:
    root = pack_tree.root("tc_flash")
    pack_dir = pack_tree.rule_pack(root, "radar", requires=[name])

    with pytest.raises(UnknownCapabilityError) as excinfo:
        pack_tree.scan_roots(root)

    assert (excinfo.value.path, excinfo.value.name) == (str(pack_dir / "rules.json"), name)


def test_an_unknown_capability_is_caught_as_a_pack_scan_error(pack_tree) -> None:
    root = pack_tree.root("tc_flash")
    pack_tree.scene(root, "tag", requires=["laser"])

    with pytest.raises(PackScanError):
        pack_tree.scan_roots(root)


def test_a_scene_requires_that_is_not_a_list_raises_malformed_scene_error(pack_tree) -> None:
    root = pack_tree.root("tc_flash")
    scene_dir = pack_tree.scene(root, "tag", requires="radio")

    with pytest.raises(MalformedSceneError) as excinfo:
        pack_tree.scan_roots(root)

    assert (excinfo.value.scene, excinfo.value.path) == ("tag", str(scene_dir / "scene.json"))


def test_a_rule_pack_requires_that_is_not_a_list_raises_malformed_manifest_error(
    pack_tree,
) -> None:
    root = pack_tree.root("tc_flash")
    pack_dir = pack_tree.rule_pack(root, "radar", requires="radio")

    with pytest.raises(MalformedManifestError) as excinfo:
        pack_tree.scan_roots(root)

    assert excinfo.value.path == str(pack_dir / "rules.json")


def test_an_effect_pack_listing_requires_raises_malformed_manifest_error(pack_tree) -> None:
    root = pack_tree.root("tc_flash")
    pack_dir = pack_tree.effect_pack(root, "basic", requires=["radio"])

    with pytest.raises(MalformedManifestError) as excinfo:
        pack_tree.scan_roots(root)

    assert excinfo.value.path == str(pack_dir / "effects.json")


# ---------------------------------------------------------------------------
# MissingCapabilityError
# ---------------------------------------------------------------------------


def test_missing_capability_error_carries_the_missing_capabilities_and_the_scene() -> None:
    error = MissingCapabilityError(frozenset({"radio", "button.B"}), "tag")

    assert isinstance(error, ValueError)
    assert (error.capabilities, error.scene) == ({"radio", "button.B"}, "tag")


def test_missing_capability_error_from_a_send_names_no_scene() -> None:
    error = MissingCapabilityError(frozenset({"ir.cone"}), None)

    assert (error.capabilities, error.scene) == ({"ir.cone"}, None)

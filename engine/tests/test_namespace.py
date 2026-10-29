"""Effect and clip lookups on the Active scene namespace.

Each test builds a namespace from a scanned Pack catalog, installs a scene
view, and resolves names through ``resolve_effect`` or ``resolve_clip``.
Failures are checked by error type and the ``name``/``kind`` they carry;
message wording is checked here once, because the namespace owns it.
"""

from __future__ import annotations

import pytest

from engine.effects.builder import EffectBuilder
from engine.namespace import (
    ActiveSceneNamespace,
    MissingPrefixError,
    NoActiveSceneError,
    UndeclaredPackError,
)
from engine.pack_catalog import PackCatalog
from engine.packs import ItemTypeError, RegistryError, UnknownItemError, UnknownPackError
from engine.scene import SceneLocalRegistry

STUB_EFFECT = (
    "from engine.tests.effects.helpers import StubEffectBuilder\nBUILD = StubEffectBuilder()\n"
)


def _catalog(pack_tree) -> PackCatalog:
    """Scan effect packs ``elements`` and ``basic`` plus scene ``arena`` with local ``win``."""
    return pack_tree.scan(
        effect_packs={"elements": {"fire": STUB_EFFECT}, "basic": {"solid": STUB_EFFECT}},
        scenes={"arena": {"effects": {"win": STUB_EFFECT}}},
    )


def _namespace(catalog: PackCatalog) -> ActiveSceneNamespace:
    return ActiveSceneNamespace(catalog.effect_registry, catalog.pack_sounds)


def _arena_locals(catalog: PackCatalog) -> SceneLocalRegistry:
    return catalog.scene_registry.get("arena").local_effect_registry


def test_scene_effect_resolves_against_installed_locals(pack_tree) -> None:
    catalog = _catalog(pack_tree)
    namespace = _namespace(catalog)
    namespace.install(_arena_locals(catalog), {}, frozenset())

    builder, pack_name, effect_name = namespace.resolve_effect("scene.win")

    assert isinstance(builder, EffectBuilder)
    assert (pack_name, effect_name) == ("scene", "win")


def test_declared_pack_effect_resolves_against_shared_packs(pack_tree) -> None:
    namespace = _namespace(_catalog(pack_tree))
    namespace.install(None, {}, frozenset({"elements"}))

    builder, pack_name, effect_name = namespace.resolve_effect("elements.fire")

    assert isinstance(builder, EffectBuilder)
    assert (pack_name, effect_name) == ("elements", "fire")


def test_installed_pack_the_scene_did_not_declare_raises_undeclared_pack(pack_tree) -> None:
    namespace = _namespace(_catalog(pack_tree))
    namespace.install(None, {}, frozenset({"basic"}))

    with pytest.raises(UndeclaredPackError) as exc_info:
        namespace.resolve_effect("elements.fire")

    error = exc_info.value
    assert (error.name, error.kind, error.pack_name) == ("elements.fire", "effect", "elements")


def test_pack_that_is_not_installed_raises_unknown_pack_even_when_declared(pack_tree) -> None:
    namespace = _namespace(_catalog(pack_tree))
    namespace.install(None, {}, frozenset({"spells"}))

    with pytest.raises(UnknownPackError) as exc_info:
        namespace.resolve_effect("spells.bolt")

    error = exc_info.value
    assert (error.name, error.kind, error.pack_name) == ("spells.bolt", "effect", "spells")


def test_unknown_pack_is_reported_before_the_declared_pack_check(pack_tree) -> None:
    namespace = _namespace(_catalog(pack_tree))
    namespace.install(None, {}, frozenset())

    with pytest.raises(UnknownPackError):
        namespace.resolve_effect("spells.bolt")


def test_unknown_effect_in_a_declared_pack_raises_unknown_item(pack_tree) -> None:
    namespace = _namespace(_catalog(pack_tree))
    namespace.install(None, {}, frozenset({"elements"}))

    with pytest.raises(UnknownItemError) as exc_info:
        namespace.resolve_effect("elements.frost")

    error = exc_info.value
    assert (error.name, error.kind) == ("elements.frost", "effect")


def test_unknown_scene_local_effect_raises_unknown_item(pack_tree) -> None:
    catalog = _catalog(pack_tree)
    namespace = _namespace(catalog)
    namespace.install(_arena_locals(catalog), {}, frozenset())

    with pytest.raises(UnknownItemError) as exc_info:
        namespace.resolve_effect("scene.lose")

    error = exc_info.value
    assert (error.name, error.kind) == ("scene.lose", "effect")


def test_scene_effect_in_a_scene_with_no_locals_raises_unknown_item(pack_tree) -> None:
    namespace = _namespace(_catalog(pack_tree))
    namespace.install(None, {}, frozenset({"elements"}))

    with pytest.raises(UnknownItemError):
        namespace.resolve_effect("scene.win")


@pytest.mark.parametrize("name", ["scene.win", "elements.fire"])
def test_any_lookup_before_install_raises_no_active_scene(pack_tree, name) -> None:
    namespace = _namespace(_catalog(pack_tree))

    with pytest.raises(NoActiveSceneError) as exc_info:
        namespace.resolve_effect(name)

    error = exc_info.value
    assert (error.name, error.kind) == (name, "effect")


def test_name_without_a_prefix_raises_missing_prefix_even_before_install(pack_tree) -> None:
    namespace = _namespace(_catalog(pack_tree))

    with pytest.raises(MissingPrefixError) as exc_info:
        namespace.resolve_effect("fire")

    error = exc_info.value
    assert (error.name, error.kind) == ("fire", "effect")


def test_reinstalling_replaces_the_previous_scene_view(pack_tree) -> None:
    catalog = _catalog(pack_tree)
    namespace = _namespace(catalog)
    namespace.install(_arena_locals(catalog), {}, frozenset({"elements"}))

    namespace.install(None, {}, frozenset({"basic"}))

    namespace.resolve_effect("basic.solid")
    with pytest.raises(UndeclaredPackError):
        namespace.resolve_effect("elements.fire")
    with pytest.raises(UnknownItemError):
        namespace.resolve_effect("scene.win")


def test_effect_with_a_bad_build_attribute_raises_the_load_fault_unchanged(pack_tree) -> None:
    catalog = pack_tree.scan(effect_packs={"broken": {"fire": "BUILD = 'not-a-builder'\n"}})
    namespace = _namespace(catalog)
    namespace.install(None, {}, frozenset({"broken"}))

    with pytest.raises(ItemTypeError):
        namespace.resolve_effect("broken.fire")


@pytest.mark.parametrize(
    ("name", "declared", "message"),
    [
        ("fire", frozenset(), "Effect name 'fire' has no 'scene.' or '<pack>.' prefix"),
        (
            "basic.solid",
            frozenset({"elements"}),
            "Effect 'basic.solid' uses pack 'basic', "
            + "which the active scene does not declare in effect_packs",
        ),
        ("spells.bolt", frozenset(), "Effect 'spells.bolt' uses unknown pack 'spells'"),
        (
            "elements.frost",
            frozenset({"elements"}),
            "Unknown effect 'elements.frost'. Available: fire",
        ),
        ("scene.lose", frozenset(), "Unknown effect 'scene.lose'. Available: win"),
    ],
)
def test_effect_errors_are_worded_from_the_name_and_kind(
    pack_tree, name, declared, message
) -> None:
    catalog = _catalog(pack_tree)
    namespace = _namespace(catalog)
    namespace.install(_arena_locals(catalog), {}, declared)

    with pytest.raises(RegistryError) as exc_info:
        namespace.resolve_effect(name)

    assert str(exc_info.value) == message


def test_no_active_scene_error_is_worded_from_the_name_and_kind(pack_tree) -> None:
    namespace = _namespace(_catalog(pack_tree))

    with pytest.raises(NoActiveSceneError) as exc_info:
        namespace.resolve_effect("elements.fire")

    assert str(exc_info.value) == "Cannot resolve effect 'elements.fire': no scene is active"


# ---------------------------------------------------------------------------
# Clip lookups
# ---------------------------------------------------------------------------


def _clip_catalog(pack_tree) -> PackCatalog:
    """Scan pack ``elements`` (sound ``crackle``), pack ``basic`` (no sounds) and two scenes.

    Scene ``arena`` has local sound ``cheer``; scene ``quiet`` has no sounds.
    """
    root = pack_tree.root("tp_clips")
    pack_tree.effect_pack(root, "elements", items={"fire": STUB_EFFECT}, sounds=["crackle"])
    pack_tree.effect_pack(root, "basic", items={"solid": STUB_EFFECT})
    pack_tree.scene(root, "arena", sounds=["cheer"])
    pack_tree.scene(root, "quiet")
    return pack_tree.scan_roots(root)


def _scene_sounds(catalog: PackCatalog, scene_name: str) -> dict[str, str]:
    return catalog.scene_registry.get(scene_name).local_sound_map


def test_scene_clip_resolves_against_installed_local_sounds(pack_tree) -> None:
    catalog = _clip_catalog(pack_tree)
    namespace = _namespace(catalog)
    sounds = _scene_sounds(catalog, "arena")
    namespace.install(None, sounds, frozenset())

    assert namespace.resolve_clip("scene.cheer") == sounds["cheer"]


def test_declared_pack_clip_resolves_against_pack_sounds(pack_tree) -> None:
    catalog = _clip_catalog(pack_tree)
    namespace = _namespace(catalog)
    namespace.install(None, {}, frozenset({"elements"}))

    assert namespace.resolve_clip("elements.crackle") == catalog.pack_sounds["elements.crackle"]


@pytest.mark.parametrize(
    ("name", "declared", "error_type"),
    [
        ("crackle", frozenset({"elements"}), MissingPrefixError),
        ("elements.crackle", frozenset({"basic"}), UndeclaredPackError),
        ("spells.zap", frozenset({"spells"}), UnknownPackError),
        ("elements.hiss", frozenset({"elements"}), UnknownItemError),
        ("scene.boo", frozenset(), UnknownItemError),
    ],
)
def test_clip_lookup_failures_raise_typed_errors_naming_the_clip(
    pack_tree, name, declared, error_type
) -> None:
    catalog = _clip_catalog(pack_tree)
    namespace = _namespace(catalog)
    namespace.install(None, _scene_sounds(catalog, "arena"), declared)

    with pytest.raises(error_type) as exc_info:
        namespace.resolve_clip(name)

    error = exc_info.value
    assert (error.name, error.kind) == (name, "clip")


@pytest.mark.parametrize("name", ["scene.cheer", "elements.crackle"])
def test_any_clip_lookup_before_install_raises_no_active_scene(pack_tree, name) -> None:
    namespace = _namespace(_clip_catalog(pack_tree))

    with pytest.raises(NoActiveSceneError) as exc_info:
        namespace.resolve_clip(name)

    error = exc_info.value
    assert (error.name, error.kind) == (name, "clip")


def test_scene_clip_in_a_scene_with_no_sounds_raises_unknown_item(pack_tree) -> None:
    catalog = _clip_catalog(pack_tree)
    namespace = _namespace(catalog)
    namespace.install(None, _scene_sounds(catalog, "quiet"), frozenset({"elements"}))

    with pytest.raises(UnknownItemError):
        namespace.resolve_clip("scene.cheer")


def test_clip_in_a_declared_pack_with_no_sounds_raises_unknown_item_not_unknown_pack(
    pack_tree,
) -> None:
    namespace = _namespace(_clip_catalog(pack_tree))
    namespace.install(None, {}, frozenset({"basic"}))

    with pytest.raises(UnknownItemError) as exc_info:
        namespace.resolve_clip("basic.thud")

    assert exc_info.value.pack_name == "basic"


def test_clip_in_a_pack_effect_resolves_against_the_active_scene_not_the_effect_pack(
    pack_tree,
) -> None:
    namespace = _namespace(_clip_catalog(pack_tree))
    namespace.install(None, {}, frozenset({"basic"}))

    with pytest.raises(UndeclaredPackError):
        namespace.resolve_clip("elements.crackle")


@pytest.mark.parametrize(
    ("name", "declared", "message"),
    [
        ("crackle", frozenset(), "Clip name 'crackle' has no 'scene.' or '<pack>.' prefix"),
        (
            "elements.crackle",
            frozenset({"basic"}),
            "Clip 'elements.crackle' uses pack 'elements', "
            + "which the active scene does not declare in effect_packs",
        ),
        ("spells.zap", frozenset(), "Clip 'spells.zap' uses unknown pack 'spells'"),
        (
            "elements.hiss",
            frozenset({"elements"}),
            "Unknown clip 'elements.hiss'. Available: crackle",
        ),
        ("scene.boo", frozenset(), "Unknown clip 'scene.boo'. Available: cheer"),
    ],
)
def test_clip_errors_are_worded_from_the_name_and_kind(pack_tree, name, declared, message) -> None:
    catalog = _clip_catalog(pack_tree)
    namespace = _namespace(catalog)
    namespace.install(None, _scene_sounds(catalog, "arena"), declared)

    with pytest.raises(RegistryError) as exc_info:
        namespace.resolve_clip(name)

    assert str(exc_info.value) == message

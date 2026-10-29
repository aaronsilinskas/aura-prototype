"""Direct tests for EffectResolver — the single seam that maps a qualified
effect name to (builder, pack_name, effect_name).

These tests exercise the resolver's public interface only: resolve(name).
They do not construct fake outputs or go through set_effect/add_effect.
"""

import pytest

from engine.effects.manager import EffectBuilder, EffectResolver
from engine.pack_catalog import scan_pack_roots
from engine.packs import PackRegistry, UnknownItemError
from engine.scene import SceneLocalRegistry

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


def _stub_item_source() -> str:
    return (
        "from engine.tests.effects.helpers import StubEffectBuilder\nBUILD = StubEffectBuilder()\n"
    )


def _invalid_build_source() -> str:
    """Module whose BUILD attribute is not an EffectBuilder instance."""
    return "BUILD = 'not-a-builder'\n"


def _no_build_source() -> str:
    """Module with no BUILD attribute at all."""
    return "# no BUILD here\n"


def _effect_registry(pack_tree, pack_name: str, items: dict[str, str]) -> PackRegistry:
    """Scan one root holding effect pack *pack_name* with *items* (item name → source)."""
    root = pack_tree.root("tr_flash")
    pack_tree.effect_pack(root, pack_name, items=items)
    return scan_pack_roots([str(root)]).effect_registry


def _local_effects(pack_tree, scene_name: str, items: dict[str, str]) -> SceneLocalRegistry:
    """Scan one root holding scene *scene_name* with local effects *items*; return its registry."""
    root = pack_tree.root("tr_flash")
    pack_tree.scene(root, scene_name, effects=items)
    return scan_pack_roots([str(root)]).scene_registry.get(scene_name).local_effect_registry


# ---------------------------------------------------------------------------
# Happy path — pack resolution
# ---------------------------------------------------------------------------


def test_resolve_returns_builder_pack_and_effect_name_for_known_effect(pack_tree) -> None:
    registry = _effect_registry(pack_tree, "elements", {"fire": _stub_item_source()})
    resolver = EffectResolver(registry)
    resolver.set_allowed_packs(frozenset({"elements"}))

    builder, pack_name, effect_name = resolver.resolve("elements.fire")

    assert isinstance(builder, EffectBuilder)
    assert pack_name == "elements"
    assert effect_name == "fire"


def test_resolve_returns_same_builder_instance_on_repeated_calls(pack_tree) -> None:
    registry = _effect_registry(pack_tree, "elements", {"fire": _stub_item_source()})
    resolver = EffectResolver(registry)
    resolver.set_allowed_packs(frozenset({"elements"}))

    builder_a, _, _ = resolver.resolve("elements.fire")
    builder_b, _, _ = resolver.resolve("elements.fire")

    assert builder_a is builder_b


# ---------------------------------------------------------------------------
# Happy path — scene-local resolution
# ---------------------------------------------------------------------------


def test_resolve_scene_prefix_returns_builder_pack_scene_and_effect_name(
    pack_tree,
) -> None:
    registry = PackRegistry()
    local_reg = _local_effects(pack_tree, "scene_a", {"flash": _stub_item_source()})
    resolver = EffectResolver(registry)
    resolver.set_local_effects(local_reg)

    builder, pack_name, effect_name = resolver.resolve("scene.flash")

    assert isinstance(builder, EffectBuilder)
    assert pack_name == "scene"
    assert effect_name == "flash"


# ---------------------------------------------------------------------------
# Error cases — malformed name
# ---------------------------------------------------------------------------


def test_resolve_raises_for_name_missing_dot_prefix() -> None:
    resolver = EffectResolver(PackRegistry())

    with pytest.raises(ValueError, match="missing pack prefix"):
        resolver.resolve("fire")


def test_resolve_error_message_includes_the_bad_name() -> None:
    resolver = EffectResolver(PackRegistry())

    with pytest.raises(ValueError, match="'fire'"):
        resolver.resolve("fire")


# ---------------------------------------------------------------------------
# Error cases — unknown pack
# ---------------------------------------------------------------------------


def test_resolve_raises_for_unknown_pack() -> None:
    """A pack declared by the active scene but absent from the registry is a wiring
    bug (the catalog checks declared packs at boot), not a membership failure —
    it still surfaces as ``UnknownPackError`` via the registry lookup.
    """
    registry = PackRegistry()
    resolver = EffectResolver(registry)
    resolver.set_allowed_packs(frozenset({"spells"}))

    with pytest.raises(ValueError, match="Unknown effect pack 'spells'"):
        resolver.resolve("spells.fireball")


# ---------------------------------------------------------------------------
# Error cases — unknown effect in known pack
# ---------------------------------------------------------------------------


def test_resolve_raises_for_unknown_effect_in_known_pack(pack_tree) -> None:
    registry = _effect_registry(pack_tree, "elements", {"fire": _stub_item_source()})
    resolver = EffectResolver(registry)
    resolver.set_allowed_packs(frozenset({"elements"}))

    with pytest.raises(ValueError, match="Unknown effect 'flash' in pack 'elements'"):
        resolver.resolve("elements.flash")


# ---------------------------------------------------------------------------
# Error cases — invalid BUILD attribute
# ---------------------------------------------------------------------------


def test_resolve_raises_for_invalid_build_attribute(pack_tree) -> None:
    registry = _effect_registry(pack_tree, "elements", {"bad": _invalid_build_source()})
    resolver = EffectResolver(registry)
    resolver.set_allowed_packs(frozenset({"elements"}))

    with pytest.raises(ValueError, match="invalid BUILD"):
        resolver.resolve("elements.bad")


# ---------------------------------------------------------------------------
# Error cases — missing BUILD attribute
# ---------------------------------------------------------------------------


def test_resolve_raises_for_missing_build_attribute(pack_tree) -> None:
    registry = _effect_registry(pack_tree, "elements", {"nobuild": _no_build_source()})
    resolver = EffectResolver(registry)
    resolver.set_allowed_packs(frozenset({"elements"}))

    with pytest.raises(ValueError, match="missing a BUILD"):
        resolver.resolve("elements.nobuild")


# ---------------------------------------------------------------------------
# Error cases — scene prefix with no active scene
# ---------------------------------------------------------------------------


def test_resolve_raises_when_scene_prefix_used_and_no_local_registry() -> None:
    resolver = EffectResolver(PackRegistry())

    with pytest.raises(ValueError, match="no scene is active"):
        resolver.resolve("scene.flash")


def test_resolve_error_includes_full_effect_name_when_no_scene() -> None:
    resolver = EffectResolver(PackRegistry())

    with pytest.raises(ValueError, match=r"scene\.flash"):
        resolver.resolve("scene.flash")


# ---------------------------------------------------------------------------
# Error cases — unknown scene-local effect
# ---------------------------------------------------------------------------


def test_resolve_raises_for_scene_local_invalid_build_attribute(pack_tree) -> None:
    registry = PackRegistry()
    local_reg = _local_effects(pack_tree, "scene_j", {"bad": _invalid_build_source()})
    resolver = EffectResolver(registry)
    resolver.set_local_effects(local_reg)

    with pytest.raises(ValueError, match="Scene-local effect 'bad' has an invalid BUILD attribute"):
        resolver.resolve("scene.bad")


def test_resolve_raises_for_scene_local_missing_build_attribute(pack_tree) -> None:
    registry = PackRegistry()
    local_reg = _local_effects(pack_tree, "scene_k", {"nobuild": _no_build_source()})
    resolver = EffectResolver(registry)
    resolver.set_local_effects(local_reg)

    with pytest.raises(
        ValueError, match="Scene-local effect 'nobuild' is missing a BUILD attribute"
    ):
        resolver.resolve("scene.nobuild")


def test_resolve_raises_for_unknown_scene_local_effect(pack_tree) -> None:
    registry = PackRegistry()
    local_reg = _local_effects(pack_tree, "scene_c", {"flash": _stub_item_source()})
    resolver = EffectResolver(registry)
    resolver.set_local_effects(local_reg)

    with pytest.raises(ValueError, match="Unknown scene-local effect 'missing'"):
        resolver.resolve("scene.missing")


def test_resolve_unknown_scene_local_effect_error_lists_available(
    pack_tree,
) -> None:
    registry = PackRegistry()
    local_reg = _local_effects(pack_tree, "scene_d", {"flash": _stub_item_source()})
    resolver = EffectResolver(registry)
    resolver.set_local_effects(local_reg)

    with pytest.raises(ValueError, match="Available:"):
        resolver.resolve("scene.missing")


# ---------------------------------------------------------------------------
# set_local_effects — enable and clear
# ---------------------------------------------------------------------------


def test_set_local_effects_none_clears_scene_prefix_resolution(pack_tree) -> None:
    registry = PackRegistry()
    local_reg = _local_effects(pack_tree, "scene_e", {"flash": _stub_item_source()})
    resolver = EffectResolver(registry)
    resolver.set_local_effects(local_reg)
    resolver.set_local_effects(None)

    with pytest.raises(ValueError, match="no scene is active"):
        resolver.resolve("scene.flash")


def test_set_local_effects_replaces_previous_registry_new_effects_resolve(pack_tree) -> None:
    registry = PackRegistry()
    local_a = _local_effects(pack_tree, "scene_f", {"a_flash": _stub_item_source()})
    local_b = _local_effects(pack_tree, "scene_g", {"b_flash": _stub_item_source()})
    resolver = EffectResolver(registry)
    resolver.set_local_effects(local_a)
    resolver.set_local_effects(local_b)

    _, _, effect_name = resolver.resolve("scene.b_flash")

    assert effect_name == "b_flash"


def test_set_local_effects_replaces_previous_registry_old_effects_no_longer_resolve(
    pack_tree,
) -> None:
    registry = PackRegistry()
    local_a = _local_effects(pack_tree, "scene_h", {"a_flash": _stub_item_source()})
    local_b = _local_effects(pack_tree, "scene_i", {"b_flash": _stub_item_source()})
    resolver = EffectResolver(registry)
    resolver.set_local_effects(local_a)
    resolver.set_local_effects(local_b)

    with pytest.raises(ValueError, match="a_flash"):
        resolver.resolve("scene.a_flash")


# ---------------------------------------------------------------------------
# Pack membership — pack.effect only resolves for packs the active scene
# declared, mirroring how scene.effect is bounded by the active scene's locals
# ---------------------------------------------------------------------------


def test_resolve_raises_when_no_allowed_packs_installed(pack_tree) -> None:
    """A fresh resolver's allowed-pack set defaults to None — fail closed."""
    registry = _effect_registry(pack_tree, "elements", {"fire": _stub_item_source()})
    resolver = EffectResolver(registry)

    with pytest.raises(ValueError, match="no scene is active"):
        resolver.resolve("elements.fire")


def test_resolve_no_active_scene_error_includes_the_effect_name(pack_tree) -> None:
    registry = _effect_registry(pack_tree, "elements", {"fire": _stub_item_source()})
    resolver = EffectResolver(registry)

    with pytest.raises(ValueError, match=r"elements\.fire"):
        resolver.resolve("elements.fire")


def test_resolve_raises_for_pack_not_declared_by_active_scene(pack_tree) -> None:
    registry = _effect_registry(pack_tree, "elements", {"fire": _stub_item_source()})
    resolver = EffectResolver(registry)
    resolver.set_allowed_packs(frozenset({"other"}))

    with pytest.raises(ValueError, match="elements"):
        resolver.resolve("elements.fire")


def test_undeclared_pack_error_does_not_say_unknown_pack(pack_tree) -> None:
    """The pack exists in the registry — it just isn't declared by the active
    scene — so the message must be honest and distinct from 'Unknown effect pack'.
    """
    registry = _effect_registry(pack_tree, "elements", {"fire": _stub_item_source()})
    resolver = EffectResolver(registry)
    resolver.set_allowed_packs(frozenset({"other"}))

    try:
        resolver.resolve("elements.fire")
    except ValueError as exc:
        assert "Unknown" not in str(exc)
    else:
        pytest.fail("expected ValueError")


def test_resolve_membership_checked_before_registry_lookup() -> None:
    """A pack absent from the registry entirely still fails with the
    not-declared message (not 'Unknown effect pack') when it also isn't
    in the allowed set — membership is checked first.
    """
    registry = PackRegistry()
    resolver = EffectResolver(registry)
    resolver.set_allowed_packs(frozenset({"other"}))

    with pytest.raises(ValueError, match="not declared"):
        resolver.resolve("spells.fireball")


def test_resolve_succeeds_for_declared_pack(pack_tree) -> None:
    registry = _effect_registry(pack_tree, "elements", {"fire": _stub_item_source()})
    resolver = EffectResolver(registry)
    resolver.set_allowed_packs(frozenset({"elements"}))

    builder, pack_name, effect_name = resolver.resolve("elements.fire")

    assert isinstance(builder, EffectBuilder)
    assert pack_name == "elements"
    assert effect_name == "fire"


def test_set_allowed_packs_none_clears_pack_prefix_resolution(pack_tree) -> None:
    registry = _effect_registry(pack_tree, "elements", {"fire": _stub_item_source()})
    resolver = EffectResolver(registry)
    resolver.set_allowed_packs(frozenset({"elements"}))
    resolver.set_allowed_packs(None)

    with pytest.raises(ValueError, match="no scene is active"):
        resolver.resolve("elements.fire")


def test_set_allowed_packs_replaces_previous_set(pack_tree) -> None:
    registry = _effect_registry(pack_tree, "elements", {"fire": _stub_item_source()})
    resolver = EffectResolver(registry)
    resolver.set_allowed_packs(frozenset({"other"}))
    resolver.set_allowed_packs(frozenset({"elements"}))

    _, pack_name, effect_name = resolver.resolve("elements.fire")

    assert pack_name == "elements"
    assert effect_name == "fire"


def test_scene_prefix_resolution_unaffected_by_missing_allowed_packs(pack_tree) -> None:
    """scene.-prefixed names are scene-local and never gated by allowed packs."""
    registry = PackRegistry()
    local_reg = _local_effects(pack_tree, "scene_m", {"flash": _stub_item_source()})
    resolver = EffectResolver(registry)
    resolver.set_local_effects(local_reg)
    # No set_allowed_packs call at all — pack.* would fail closed, but scene.* must not.

    builder, pack_name, effect_name = resolver.resolve("scene.flash")

    assert isinstance(builder, EffectBuilder)
    assert pack_name == "scene"
    assert effect_name == "flash"


# ---------------------------------------------------------------------------
# Anti-regression — dispatch is by exception type, never by message text
# ---------------------------------------------------------------------------


class _WrongWordingRegistry:
    """Stub registry whose ``.get`` raises a typed error with deliberately
    wrong wording, to prove the resolver dispatches on exception type rather
    than parsing ``str(exc)``.
    """

    def __init__(self, error: Exception) -> None:
        self._error = error

    def get(self, pack_name: str, item_name: str, expected_class: type) -> object:
        raise self._error


def test_resolve_pack_error_message_is_canonical_even_when_typed_error_wording_is_wrong() -> None:
    stub_registry = _WrongWordingRegistry(
        UnknownItemError("totally different name", ["nope"], pack_name="totally different pack")
    )
    resolver = EffectResolver(stub_registry)  # type: ignore[arg-type]
    resolver.set_allowed_packs(frozenset({"spells"}))

    with pytest.raises(ValueError, match="Unknown effect 'fireball' in pack 'spells'"):
        resolver.resolve("spells.fireball")

import pytest

from engine.state import EffectControls, EffectReceipt, GameState, SceneControls, Scope, ScopeValue

# ---------------------------------------------------------------------------
# GameState.get_or_none
# ---------------------------------------------------------------------------


def _make_state() -> GameState:
    return GameState(effect_controls=EffectControls(), scene_controls=SceneControls())


def test_get_or_none_returns_none_when_key_absent() -> None:
    state = _make_state()

    assert state.get_or_none("missing", str) is None


def test_get_or_none_returns_value_when_present_and_matching_type() -> None:
    state = _make_state()
    state.set("name", "aura")

    assert state.get_or_none("name", str) == "aura"


def test_get_or_none_raises_value_error_when_type_mismatch() -> None:
    state = _make_state()
    state.set("name", 123)

    with pytest.raises(ValueError):
        state.get_or_none("name", str)


# ---------------------------------------------------------------------------
# ScopeValue — leaf scopes
# ---------------------------------------------------------------------------


def test_leaf_scope_key_matches_its_value() -> None:
    scope = ScopeValue("personal")

    assert scope.keys == ("personal",)


def test_leaf_scope_members_contains_only_itself() -> None:
    scope = ScopeValue("personal")

    assert scope.members == [scope]


def test_leaf_scope_repr_is_its_value_string() -> None:
    scope = ScopeValue("personal")

    assert repr(scope) == "personal"


# ---------------------------------------------------------------------------
# ScopeValue — composite scopes
# ---------------------------------------------------------------------------


def test_composite_scope_keys_are_union_of_member_keys() -> None:
    a = ScopeValue("a")
    b = ScopeValue("b")
    composite = ScopeValue("ab", [a, b])

    assert composite.keys == ("a", "b")


def test_composite_scope_members_are_the_provided_list() -> None:
    a = ScopeValue("a")
    b = ScopeValue("b")
    composite = ScopeValue("ab", [a, b])

    assert composite.members == [a, b]


def test_nested_composite_scope_flattens_keys_transitively() -> None:
    a = ScopeValue("a")
    b = ScopeValue("b")
    c = ScopeValue("c")
    inner = ScopeValue("ab", [a, b])
    outer = ScopeValue("abc", [inner, c])

    assert outer.keys == ("a", "b", "c")


def test_nested_composite_scope_members_are_direct_children_not_leaves() -> None:
    a = ScopeValue("a")
    b = ScopeValue("b")
    c = ScopeValue("c")
    inner = ScopeValue("ab", [a, b])
    outer = ScopeValue("abc", [inner, c])

    assert outer.members == [inner, c]


# ---------------------------------------------------------------------------
# Scope constants — leaf keys
# ---------------------------------------------------------------------------


def test_personal_scope_routes_to_personal_key() -> None:
    assert Scope.PERSONAL.keys == ("personal",)


def test_directional_scope_routes_to_directional_key() -> None:
    assert Scope.DIRECTIONAL.keys == ("directional",)


def test_global_main_scope_routes_to_global_main_key() -> None:
    assert Scope.Global.MAIN.keys == ("global.main",)


def test_global_buff_scope_routes_to_global_buff_key() -> None:
    assert Scope.Global.BUFF.keys == ("global.buff",)


def test_global_debuff_scope_routes_to_global_debuff_key() -> None:
    assert Scope.Global.DEBUFF.keys == ("global.debuff",)


# ---------------------------------------------------------------------------
# Scope constants — composite expansion
# ---------------------------------------------------------------------------


def test_global_all_expands_to_all_three_global_zones() -> None:
    assert set(Scope.Global.ALL.keys) == {"global.main", "global.buff", "global.debuff"}


def test_scope_all_expands_to_every_registered_output() -> None:
    assert set(Scope.ALL.keys) == {
        "personal",
        "directional",
        "global.main",
        "global.buff",
        "global.debuff",
        "ambient",
    }


def test_scope_all_contains_no_duplicate_keys() -> None:
    keys = Scope.ALL.keys

    assert len(keys) == len(set(keys))


def test_global_all_keys_are_subset_of_scope_all_keys() -> None:
    assert set(Scope.Global.ALL.keys).issubset(set(Scope.ALL.keys))


# ---------------------------------------------------------------------------
# Scope constants — AMBIENT and NON_AMBIENT
# ---------------------------------------------------------------------------


def test_ambient_scope_routes_to_ambient_key() -> None:
    assert Scope.AMBIENT.keys == ("ambient",)


def test_ambient_scope_is_a_leaf() -> None:
    assert Scope.AMBIENT.members == [Scope.AMBIENT]


def test_non_ambient_expands_to_personal_directional_and_global() -> None:
    assert set(Scope.NON_AMBIENT.keys) == {
        "personal",
        "directional",
        "global.main",
        "global.buff",
        "global.debuff",
    }


def test_non_ambient_does_not_include_ambient_key() -> None:
    assert "ambient" not in Scope.NON_AMBIENT.keys


def test_scope_all_includes_ambient() -> None:
    assert "ambient" in Scope.ALL.keys


# ---------------------------------------------------------------------------
# EffectReceipt — brightness and loudness slots
# ---------------------------------------------------------------------------


def test_effect_receipt_brightness_defaults_to_one() -> None:
    receipt = EffectReceipt(1)

    assert receipt.brightness == 1.0


def test_effect_receipt_loudness_defaults_to_one() -> None:
    receipt = EffectReceipt(1)

    assert receipt.loudness == 1.0


def test_effect_receipt_brightness_is_writable() -> None:
    receipt = EffectReceipt(1)
    receipt.brightness = 0.5

    assert receipt.brightness == 0.5


def test_effect_receipt_loudness_is_writable() -> None:
    receipt = EffectReceipt(1)
    receipt.loudness = 0.25

    assert receipt.loudness == 0.25


def test_effect_receipt_constructor_accepts_only_effect_id() -> None:
    receipt = EffectReceipt(42)

    assert receipt.id == 42

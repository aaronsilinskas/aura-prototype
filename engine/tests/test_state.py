import pytest

from engine.state import (
    EffectControls,
    EffectReceipt,
    GameState,
    SceneControls,
    Scope,
    ScopeValue,
    StateSlot,
)

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


# ---------------------------------------------------------------------------
# StateSlot
# ---------------------------------------------------------------------------


class _Marker:
    __slots__ = ()


def _make_slot(key: str = "test_slot") -> StateSlot:
    return StateSlot(key, lambda s: _Marker(), _Marker)


def test_state_slot_exposes_key_used_to_store_value_in_game_state() -> None:
    slot = StateSlot("my_key", lambda s: _Marker(), _Marker)

    assert slot.key == "my_key"


def test_state_slot_builds_value_via_factory_on_first_call() -> None:
    slot = _make_slot()
    state = _make_state()

    result = slot(state)

    assert isinstance(result, _Marker)


def test_state_slot_cache_hit_returns_the_same_instance() -> None:
    slot = _make_slot()
    state = _make_state()

    first = slot(state)
    second = slot(state)

    assert first is second


def test_state_slot_factory_is_called_with_the_game_state() -> None:
    received: list[GameState] = []

    def factory(s: GameState) -> _Marker:
        received.append(s)
        return _Marker()

    slot = StateSlot("factory_slot", factory, _Marker)
    state = _make_state()

    slot(state)

    assert received == [state]


def test_state_slot_factory_is_not_called_again_on_cache_hit() -> None:
    call_count = [0]

    def factory(s: GameState) -> _Marker:
        call_count[0] += 1
        return _Marker()

    slot = StateSlot("counted_slot", factory, _Marker)
    state = _make_state()

    slot(state)
    slot(state)

    assert call_count[0] == 1


def test_state_slot_distinct_keys_produce_independent_values() -> None:
    slot_a = StateSlot("slot_a", lambda s: _Marker(), _Marker)
    slot_b = StateSlot("slot_b", lambda s: _Marker(), _Marker)
    state = _make_state()

    a = slot_a(state)
    b = slot_b(state)

    assert a is not b


def test_state_slot_raises_when_pre_seeded_value_has_wrong_type() -> None:
    slot = _make_slot("typed_slot")
    state = _make_state()
    state.set("typed_slot", "wrong type")

    with pytest.raises(ValueError):
        slot(state)


def test_state_slot_is_independent_across_separate_game_state_instances() -> None:
    slot = _make_slot()
    state1 = _make_state()
    state2 = _make_state()

    v1 = slot(state1)
    v2 = slot(state2)

    assert v1 is not v2


# ---------------------------------------------------------------------------
# StateSlot — two slots sharing a key resolve the same cached value
# ---------------------------------------------------------------------------


def test_two_state_slots_with_the_same_key_resolve_the_same_cached_value() -> None:
    shared_key = "shared_machine"
    slot_a = StateSlot(shared_key, lambda s: _Marker(), _Marker)
    slot_b = StateSlot(shared_key, lambda s: _Marker(), _Marker)
    state = _make_state()

    a = slot_a(state)
    b = slot_b(state)

    assert a is b


# ---------------------------------------------------------------------------
# StateSlot.is_in
# ---------------------------------------------------------------------------


def test_state_slot_is_in_returns_false_before_first_call() -> None:
    slot = _make_slot()
    state = _make_state()

    assert not slot.is_in(state)


def test_state_slot_is_in_returns_true_after_first_call() -> None:
    slot = _make_slot()
    state = _make_state()
    slot(state)

    assert slot.is_in(state)


def test_state_slot_is_in_is_false_after_key_deleted_from_state() -> None:
    slot = _make_slot()
    state = _make_state()
    slot(state)
    state.delete(slot.key)

    assert not slot.is_in(state)

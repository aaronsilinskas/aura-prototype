from effects.effect import EffectState, EffectStep, SharedStateKey

# ---------------------------------------------------------------------------
# Shared data — read and write across steps
# ---------------------------------------------------------------------------


def test_shared_data_written_by_one_step_is_readable_by_another() -> None:
    key = SharedStateKey()
    state = EffectState()

    state.set_shared_data(key, 42)

    assert state.get_shared_data(key, int) == 42


def test_shared_data_returns_none_before_any_value_is_stored() -> None:
    key = SharedStateKey()
    state = EffectState()

    assert state.get_shared_data(key, int) is None


def test_shared_data_can_be_updated_by_overwriting_the_same_key() -> None:
    key = SharedStateKey()
    state = EffectState()

    state.set_shared_data(key, "first")
    state.set_shared_data(key, "second")

    assert state.get_shared_data(key, str) == "second"


def test_two_different_keys_store_independent_values() -> None:
    key_a = SharedStateKey()
    key_b = SharedStateKey()
    state = EffectState()

    state.set_shared_data(key_a, 1)
    state.set_shared_data(key_b, 2)

    assert state.get_shared_data(key_a, int) == 1
    assert state.get_shared_data(key_b, int) == 2


def test_remove_shared_data_makes_key_return_none_afterwards() -> None:
    key = SharedStateKey()
    state = EffectState()
    state.set_shared_data(key, "value")

    state.remove_shared_data(key)

    assert state.get_shared_data(key, str) is None


def test_remove_shared_data_on_unset_key_does_not_raise() -> None:
    key = SharedStateKey()
    state = EffectState()

    state.remove_shared_data(key)  # should not raise


# ---------------------------------------------------------------------------
# Shared data is distinct from per-step data
# ---------------------------------------------------------------------------


def test_shared_data_is_unaffected_by_step_data_writes() -> None:
    key = SharedStateKey()
    step = EffectStep.__new__(EffectStep)
    state = EffectState()

    state.set_shared_data(key, "shared")
    state.set_step_data(step, "per-step")

    assert state.get_shared_data(key, str) == "shared"


def test_step_data_is_unaffected_by_shared_data_writes() -> None:
    key = SharedStateKey()
    step = EffectStep.__new__(EffectStep)
    state = EffectState()

    state.set_shared_data(key, "shared")
    state.set_step_data(step, "per-step")

    assert state.get_step_data(step, str) == "per-step"


# ---------------------------------------------------------------------------
# Per-step data isolation (complement to the shared-data tests)
# ---------------------------------------------------------------------------


def test_step_data_set_by_one_step_is_not_visible_to_a_different_step_instance() -> (
    None
):
    step_a = EffectStep.__new__(EffectStep)
    step_b = EffectStep.__new__(EffectStep)
    state = EffectState()

    state.set_step_data(step_a, "a-data")

    assert state.get_step_data(step_b, str) is None


def test_remove_step_data_on_unset_key_does_not_raise() -> None:
    step = EffectStep.__new__(EffectStep)
    state = EffectState()

    state.remove_step_data(step)  # should not raise

from effects.manager.manager import EffectManager
from effects.manager.scope import Scope
from effects.tests.manager.helpers import SpyEffectOutput, StubEffectBuilder
from engine.timer import Timer


def _make_timer() -> Timer:
    return Timer()


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_effect_manager_accepts_builder_and_outputs() -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])

    EffectManager(builder=StubEffectBuilder(), outputs=[output])


def test_effect_manager_accepts_empty_outputs_list() -> None:
    EffectManager(builder=StubEffectBuilder(), outputs=[])


# ---------------------------------------------------------------------------
# update — go-dark signal when no effects are active
# ---------------------------------------------------------------------------


def test_update_with_no_effects_sends_go_dark_to_output() -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(builder=StubEffectBuilder(), outputs=[output])

    manager.update(_make_timer())

    assert output.update_pixels_calls == [[]]


def test_update_with_no_effects_sends_go_dark_to_all_outputs() -> None:
    output_a = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_b = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(builder=StubEffectBuilder(), outputs=[output_a, output_b])

    manager.update(_make_timer())

    assert output_a.update_pixels_calls == [[]]
    assert output_b.update_pixels_calls == [[]]


def test_update_called_twice_notifies_output_each_tick() -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(builder=StubEffectBuilder(), outputs=[output])

    manager.update(_make_timer())
    manager.update(_make_timer())

    assert len(output.update_pixels_calls) == 2

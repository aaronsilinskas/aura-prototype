"""Tests for ElementBrowserRule — initial display, button A (page advance),
and button B (level step).

Behavior coverage:
- First dispatch renders page 0 at level 1 across all five scopes
- Second button-less dispatch does NOT re-render (once-only init guard)
- Button A advances page 0 → 1 at current level; preserves level
- Button A wraps page 1 → 0 at current level
- Button B steps level 1 → 2; re-applies current page; preserves page
- Button B wraps level 10 → 1; re-applies current page
"""

from __future__ import annotations

import pytest

from engine.engine import GameEngine
from engine.input import ButtonData, InputEvents
from engine.state import GameState, SceneControls, Scope
from engine.tests.helpers import SpyEffectControls
from packs.scenes.element_browser.rules.browser_rule import ElementBrowserRule

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

_PAGE_0_SCOPES = [
    Scope.Global.BUFF,
    Scope.Global.DEBUFF,
    Scope.Global.MAIN,
    Scope.DIRECTIONAL,
    Scope.PERSONAL,
]
_PAGE_0_EFFECTS = [
    "elements.air",
    "elements.dark",
    "elements.earth",
    "elements.fire",
    "elements.gravity",
]
_PAGE_1_SCOPES = [
    Scope.Global.BUFF,
    Scope.Global.DEBUFF,
    Scope.Global.MAIN,
    Scope.DIRECTIONAL,
    Scope.PERSONAL,
]
_PAGE_1_EFFECTS = [
    "elements.ice",
    "elements.light",
    "elements.lightning",
    "elements.time",
    "elements.water",
]


@pytest.fixture()
def spy() -> SpyEffectControls:
    return SpyEffectControls()


def _make_state(
    spy: SpyEffectControls,
    initial_data: dict | None = None,
) -> tuple[GameState, GameEngine]:
    engine = GameEngine(spy)  # pyright: ignore[reportArgumentType]
    engine.add_rules(ElementBrowserRule())
    defaults = {"page": 0, "level": 1}
    state = engine.create_state(SceneControls(), initial_data=initial_data or defaults)
    return state, engine


def _no_button_event() -> InputEvents.ButtonAndAcceleration:
    return InputEvents.ButtonAndAcceleration(ButtonData(states={}))


def _button_a_event() -> InputEvents.ButtonAndAcceleration:
    return InputEvents.ButtonAndAcceleration(ButtonData(states={"A": ButtonData.PRESSED}))


def _button_b_event() -> InputEvents.ButtonAndAcceleration:
    return InputEvents.ButtonAndAcceleration(ButtonData(states={"B": ButtonData.PRESSED}))


def _dispatch(
    state: GameState, engine: GameEngine, event: InputEvents.ButtonAndAcceleration
) -> None:
    state.queue_event(event)
    engine.update(state)


# ---------------------------------------------------------------------------
# Initial display — first dispatch renders page 0 at level 1
# ---------------------------------------------------------------------------


def test_first_dispatch_sets_all_page0_effects_at_level_1(spy):
    state, engine = _make_state(spy)

    _dispatch(state, engine, _no_button_event())

    assert len(spy.set_effect_calls) == 5
    for i, (scope, name, opts) in enumerate(spy.set_effect_calls):
        assert scope is _PAGE_0_SCOPES[i]
        assert name == _PAGE_0_EFFECTS[i]
        assert opts == {"level": 1}


def test_first_dispatch_uses_initial_data_level(spy):
    state, engine = _make_state(spy, initial_data={"page": 0, "level": 3})

    _dispatch(state, engine, _no_button_event())

    for _, _, opts in spy.set_effect_calls:
        assert opts == {"level": 3}


# ---------------------------------------------------------------------------
# Once-only initial render guard
# ---------------------------------------------------------------------------


def test_second_no_button_dispatch_does_not_re_render_page0(spy):
    state, engine = _make_state(spy)

    _dispatch(state, engine, _no_button_event())
    spy.set_effect_calls.clear()

    _dispatch(state, engine, _no_button_event())

    assert spy.set_effect_calls == []


# ---------------------------------------------------------------------------
# Button A — advance page
# ---------------------------------------------------------------------------


def test_button_a_advances_from_page0_to_page1(spy):
    state, engine = _make_state(spy)
    _dispatch(state, engine, _no_button_event())  # initial render
    spy.set_effect_calls.clear()

    _dispatch(state, engine, _button_a_event())

    assert len(spy.set_effect_calls) == 5
    for i, (scope, name, _opts) in enumerate(spy.set_effect_calls):
        assert scope is _PAGE_1_SCOPES[i]
        assert name == _PAGE_1_EFFECTS[i]


def test_button_a_preserves_current_level(spy):
    state, engine = _make_state(spy, initial_data={"page": 0, "level": 5})
    _dispatch(state, engine, _no_button_event())
    spy.set_effect_calls.clear()

    _dispatch(state, engine, _button_a_event())

    for _, _, opts in spy.set_effect_calls:
        assert opts == {"level": 5}


def test_button_a_wraps_page1_back_to_page0(spy):
    state, engine = _make_state(spy, initial_data={"page": 1, "level": 1})
    _dispatch(state, engine, _no_button_event())  # initial render of page 1
    spy.set_effect_calls.clear()

    _dispatch(state, engine, _button_a_event())

    assert len(spy.set_effect_calls) == 5
    for i, (scope, name, _) in enumerate(spy.set_effect_calls):
        assert scope is _PAGE_0_SCOPES[i]
        assert name == _PAGE_0_EFFECTS[i]


# ---------------------------------------------------------------------------
# Button B — step level
# ---------------------------------------------------------------------------


def test_button_b_increments_level_and_reapplies_current_page(spy):
    state, engine = _make_state(spy, initial_data={"page": 0, "level": 1})
    _dispatch(state, engine, _no_button_event())
    spy.set_effect_calls.clear()

    _dispatch(state, engine, _button_b_event())

    assert len(spy.set_effect_calls) == 5
    for _, _, opts in spy.set_effect_calls:
        assert opts == {"level": 2}


def test_button_b_preserves_current_page(spy):
    state, engine = _make_state(spy, initial_data={"page": 1, "level": 2})
    _dispatch(state, engine, _no_button_event())
    spy.set_effect_calls.clear()

    _dispatch(state, engine, _button_b_event())

    for i, (scope, name, _) in enumerate(spy.set_effect_calls):
        assert scope is _PAGE_1_SCOPES[i]
        assert name == _PAGE_1_EFFECTS[i]


def test_button_b_wraps_level_10_to_1(spy):
    state, engine = _make_state(spy, initial_data={"page": 0, "level": 10})
    _dispatch(state, engine, _no_button_event())
    spy.set_effect_calls.clear()

    _dispatch(state, engine, _button_b_event())

    for _, _, opts in spy.set_effect_calls:
        assert opts == {"level": 1}

"""Tests for ``LobbySelectRule``: config-driven multi-scope preview + selection.

Uses ``SpyEffectControls`` to assert which effects start on which scopes, and
``RecordingSceneControls`` (this pack's reboot fake, mirroring issue #910's
``RecordingSceneReboot`` on the rule-facing ``SceneControls`` seam) to assert
Button B's ``reboot_into`` call.
"""

from __future__ import annotations

import pytest

from engine.engine import GameEngine
from engine.input import ButtonData, InputEvents
from engine.state import GameState, Scope
from engine.tests.helpers import SpyEffectControls
from packs.rules.lobby.lobby_select_rule import LobbySelectRule
from packs.rules.lobby.tests.helpers import RecordingSceneControls

_SCOPES = ["personal", "global.main", "directional"]
_RESOLVED_SCOPES = [Scope.PERSONAL, Scope.Global.MAIN, Scope.DIRECTIONAL]

_ENTRIES = [
    {"scene": "hardware_test", "effect": "elements.fire", "options": {"level": 5}},
    {"scene": "element_browser", "effect": "elements.water", "options": {"level": 3}},
    {"scene": "red_light_green_light", "effect": "elements.earth", "options": {"level": 1}},
    {"scene": "tag", "effect": "elements.ice", "options": {"level": 7}},
]


def _lobby_data(scopes: list | None = None, entries: list | None = None) -> dict:
    return {
        "lobby": {
            "scopes": _SCOPES if scopes is None else scopes,
            "entries": _ENTRIES if entries is None else entries,
        }
    }


@pytest.fixture()
def spy() -> SpyEffectControls:
    return SpyEffectControls()


@pytest.fixture()
def reboot() -> RecordingSceneControls:
    return RecordingSceneControls()


def _make_state(
    spy: SpyEffectControls,
    reboot: RecordingSceneControls,
    initial_data: dict | None = None,
    rule: LobbySelectRule | None = None,
) -> tuple[GameState, GameEngine]:
    engine = GameEngine(spy)  # pyright: ignore[reportArgumentType]
    engine.add_rules(rule if rule is not None else LobbySelectRule())
    state = engine.create_state(
        reboot, initial_data=initial_data if initial_data is not None else _lobby_data()
    )
    return state, engine


def _no_button_event() -> InputEvents.Sensors:
    return InputEvents.Sensors(ButtonData(states={}))


def _button_a_event() -> InputEvents.Sensors:
    return InputEvents.Sensors(ButtonData(states={"A": ButtonData.PRESSED}))


def _button_b_event() -> InputEvents.Sensors:
    return InputEvents.Sensors(ButtonData(states={"B": ButtonData.PRESSED}))


def _dispatch(state: GameState, engine: GameEngine, event: InputEvents.Sensors) -> None:
    state.queue_event(event)
    engine.update(state)


# ---------------------------------------------------------------------------
# First tick — full window paint
# ---------------------------------------------------------------------------


def test_first_tick_paints_every_scope_from_selection_0(spy, reboot):
    state, engine = _make_state(spy, reboot)

    _dispatch(state, engine, _no_button_event())

    assert spy.set_effect_calls == [
        (Scope.PERSONAL, "elements.fire", {"level": 5}),
        (Scope.Global.MAIN, "elements.water", {"level": 3}),
        (Scope.DIRECTIONAL, "elements.earth", {"level": 1}),
    ]


def test_second_no_button_dispatch_does_not_repaint(spy, reboot):
    state, engine = _make_state(spy, reboot)
    _dispatch(state, engine, _no_button_event())
    spy.set_effect_calls.clear()

    _dispatch(state, engine, _no_button_event())

    assert spy.set_effect_calls == []


# ---------------------------------------------------------------------------
# Button A — advance selection, repaint every scope
# ---------------------------------------------------------------------------


def test_button_a_advances_selection_and_repaints_every_scope(spy, reboot):
    state, engine = _make_state(spy, reboot)
    _dispatch(state, engine, _no_button_event())
    spy.set_effect_calls.clear()

    _dispatch(state, engine, _button_a_event())

    assert spy.set_effect_calls == [
        (Scope.PERSONAL, "elements.water", {"level": 3}),
        (Scope.Global.MAIN, "elements.earth", {"level": 1}),
        (Scope.DIRECTIONAL, "elements.ice", {"level": 7}),
    ]


def test_button_a_wraps_past_the_last_entry_back_to_the_first(spy, reboot):
    state, engine = _make_state(spy, reboot)
    _dispatch(state, engine, _no_button_event())
    for _ in range(len(_ENTRIES) - 1):
        _dispatch(state, engine, _button_a_event())
    spy.set_effect_calls.clear()

    _dispatch(state, engine, _button_a_event())  # advances index 3 -> 0

    assert spy.set_effect_calls[0] == (Scope.PERSONAL, "elements.fire", {"level": 5})


def test_fewer_entries_than_scopes_shows_duplicates_but_fills_every_scope(spy, reboot):
    state, engine = _make_state(spy, reboot, initial_data=_lobby_data(entries=_ENTRIES[:2]))

    _dispatch(state, engine, _no_button_event())

    assert spy.set_effect_calls == [
        (Scope.PERSONAL, "elements.fire", {"level": 5}),
        (Scope.Global.MAIN, "elements.water", {"level": 3}),
        (Scope.DIRECTIONAL, "elements.fire", {"level": 5}),  # wraps back to entry 0
    ]


# ---------------------------------------------------------------------------
# Button B — reboot into the current selection
# ---------------------------------------------------------------------------


def test_button_b_reboots_into_the_initial_selection(spy, reboot):
    state, engine = _make_state(spy, reboot)
    _dispatch(state, engine, _no_button_event())

    _dispatch(state, engine, _button_b_event())

    assert reboot.reboot_into_calls == ["hardware_test"]


def test_button_b_reboots_into_the_advanced_selection(spy, reboot):
    state, engine = _make_state(spy, reboot)
    _dispatch(state, engine, _no_button_event())
    _dispatch(state, engine, _button_a_event())

    _dispatch(state, engine, _button_b_event())

    assert reboot.reboot_into_calls == ["element_browser"]


def test_button_b_does_not_repaint_any_scope(spy, reboot):
    state, engine = _make_state(spy, reboot)
    _dispatch(state, engine, _no_button_event())
    spy.set_effect_calls.clear()

    _dispatch(state, engine, _button_b_event())

    assert spy.set_effect_calls == []


# ---------------------------------------------------------------------------
# Invalid config is rejected
# ---------------------------------------------------------------------------


def test_empty_scopes_is_rejected(spy, reboot):
    state, engine = _make_state(spy, reboot, initial_data=_lobby_data(scopes=[]))

    with pytest.raises(ValueError, match="scopes"):
        _dispatch(state, engine, _no_button_event())


def test_empty_entries_is_rejected(spy, reboot):
    state, engine = _make_state(spy, reboot, initial_data=_lobby_data(entries=[]))

    with pytest.raises(ValueError, match="entries"):
        _dispatch(state, engine, _no_button_event())


def test_missing_lobby_config_is_rejected(spy, reboot):
    state, engine = _make_state(spy, reboot, initial_data={})

    with pytest.raises(ValueError, match="lobby"):
        _dispatch(state, engine, _no_button_event())


# ---------------------------------------------------------------------------
# Default-overridable config key (à la FpsLoggerRule's enabled_key)
# ---------------------------------------------------------------------------


def test_custom_config_key_reads_config_from_that_key_instead_of_lobby(spy, reboot):
    state, engine = _make_state(
        spy,
        reboot,
        initial_data={
            "my_lobby": {
                "scopes": ["personal"],
                "entries": [{"scene": "hardware_test", "effect": "elements.fire", "options": {}}],
            }
        },
        rule=LobbySelectRule(config_key="my_lobby"),
    )

    _dispatch(state, engine, _no_button_event())

    assert spy.set_effect_calls == [(Scope.PERSONAL, "elements.fire", {})]


def test_default_config_key_ignores_a_differently_keyed_config(spy, reboot):
    state, engine = _make_state(
        spy,
        reboot,
        initial_data={"not_lobby": {"scopes": ["personal"], "entries": [_ENTRIES[0]]}},
    )

    with pytest.raises(ValueError, match="lobby"):
        _dispatch(state, engine, _no_button_event())

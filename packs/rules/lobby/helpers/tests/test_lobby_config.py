"""Tests for ``LobbyConfig``, ``LobbyEntry``, and the lobby-local ``scope_by_name`` resolver."""

from __future__ import annotations

import pytest

from engine.engine import GameEngine
from engine.state import GameState, SceneControls, Scope
from engine.tests.helpers import SpyEffectControls
from packs.rules.lobby.helpers.lobby_config import LobbyConfig, LobbyEntry, scope_by_name


def _make_state(initial_data: dict | None = None) -> GameState:
    spy = SpyEffectControls()
    engine = GameEngine(spy)  # pyright: ignore[reportArgumentType]
    return engine.create_state(SceneControls(), initial_data=initial_data or {})


# ---------------------------------------------------------------------------
# scope_by_name
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,expected",
    [
        ("personal", Scope.PERSONAL),
        ("directional", Scope.DIRECTIONAL),
        ("ambient", Scope.AMBIENT),
        ("global.main", Scope.Global.MAIN),
        ("global.buff", Scope.Global.BUFF),
        ("global.debuff", Scope.Global.DEBUFF),
        ("global.all", Scope.Global.ALL),
        ("non_ambient", Scope.NON_AMBIENT),
        ("all", Scope.ALL),
    ],
)
def test_scope_by_name_resolves_every_known_scope(name, expected):
    assert scope_by_name(name) is expected


def test_scope_by_name_raises_naming_the_unknown_scope():
    with pytest.raises(ValueError, match="not-a-real-scope"):
        scope_by_name("not-a-real-scope")


# ---------------------------------------------------------------------------
# LobbyConfig.__init__ — direct construction validation
# ---------------------------------------------------------------------------


def test_construction_rejects_empty_scopes():
    with pytest.raises(ValueError, match="scopes"):
        LobbyConfig(scopes=[], entries=[LobbyEntry("hardware_test", "elements.fire", {})])


def test_construction_rejects_empty_entries():
    with pytest.raises(ValueError, match="entries"):
        LobbyConfig(scopes=[Scope.PERSONAL], entries=[])


def test_construction_accepts_a_single_scope_and_single_entry():
    config = LobbyConfig(
        scopes=[Scope.PERSONAL],
        entries=[LobbyEntry("hardware_test", "elements.fire", {"level": 5})],
    )

    assert config.scopes == [Scope.PERSONAL]
    assert config.entries[0].scene == "hardware_test"


# ---------------------------------------------------------------------------
# LobbyConfig.from_state
# ---------------------------------------------------------------------------


def test_from_state_resolves_scopes_and_entries_in_order():
    state = _make_state(
        {
            "lobby": {
                "scopes": ["personal", "global.main"],
                "entries": [
                    {"scene": "hardware_test", "effect": "elements.fire", "options": {"level": 5}},
                    {"scene": "tag", "effect": "elements.ice", "options": {"level": 3}},
                ],
            }
        }
    )

    config = LobbyConfig.from_state(state, "lobby")

    assert config.scopes == [Scope.PERSONAL, Scope.Global.MAIN]
    assert [e.scene for e in config.entries] == ["hardware_test", "tag"]
    assert [e.effect for e in config.entries] == ["elements.fire", "elements.ice"]
    assert config.entries[0].options == {"level": 5}


def test_from_state_defaults_missing_options_to_empty_dict():
    state = _make_state(
        {
            "lobby": {
                "scopes": ["personal"],
                "entries": [{"scene": "hardware_test", "effect": "elements.fire"}],
            }
        }
    )

    config = LobbyConfig.from_state(state, "lobby")

    assert config.entries[0].options == {}


def test_from_state_reads_a_custom_config_key():
    state = _make_state(
        {
            "my_lobby": {
                "scopes": ["personal"],
                "entries": [{"scene": "hardware_test", "effect": "elements.fire"}],
            }
        }
    )

    config = LobbyConfig.from_state(state, "my_lobby")

    assert config.scopes == [Scope.PERSONAL]


def test_from_state_raises_when_config_key_is_absent():
    state = _make_state({})

    with pytest.raises(ValueError, match="lobby"):
        LobbyConfig.from_state(state, "lobby")


def test_from_state_raises_when_config_value_is_not_a_dict():
    state = _make_state({"lobby": "not-a-dict"})

    with pytest.raises(ValueError, match="lobby"):
        LobbyConfig.from_state(state, "lobby")


def test_from_state_raises_on_empty_scopes():
    state = _make_state(
        {
            "lobby": {
                "scopes": [],
                "entries": [{"scene": "hardware_test", "effect": "elements.fire"}],
            }
        }
    )

    with pytest.raises(ValueError, match="scopes"):
        LobbyConfig.from_state(state, "lobby")


def test_from_state_raises_on_empty_entries():
    state = _make_state({"lobby": {"scopes": ["personal"], "entries": []}})

    with pytest.raises(ValueError, match="entries"):
        LobbyConfig.from_state(state, "lobby")


def test_from_state_raises_on_unknown_scope_name():
    state = _make_state(
        {
            "lobby": {
                "scopes": ["not-a-real-scope"],
                "entries": [{"scene": "hardware_test", "effect": "elements.fire"}],
            }
        }
    )

    with pytest.raises(ValueError, match="not-a-real-scope"):
        LobbyConfig.from_state(state, "lobby")


def test_from_state_raises_on_entry_missing_scene():
    state = _make_state(
        {"lobby": {"scopes": ["personal"], "entries": [{"effect": "elements.fire"}]}}
    )

    with pytest.raises(ValueError, match="scene"):
        LobbyConfig.from_state(state, "lobby")


def test_from_state_raises_on_entry_missing_effect():
    state = _make_state(
        {"lobby": {"scopes": ["personal"], "entries": [{"scene": "hardware_test"}]}}
    )

    with pytest.raises(ValueError, match="effect"):
        LobbyConfig.from_state(state, "lobby")

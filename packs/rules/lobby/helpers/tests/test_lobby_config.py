"""Tests for ``LobbyConfig``, ``LobbyEntry``, and the lobby-local ``scope_by_name`` resolver."""

from __future__ import annotations

import pytest

from engine.settings import Settings
from engine.state import Scope
from packs.rules.lobby.helpers.lobby_config import LobbyConfig, scope_by_name
from packs.tests.settings_helper import settings_for


def _lobby_settings(scopes: list, entries: list) -> Settings:
    return settings_for(rule_packs={"lobby": {"scopes": scopes, "entries": entries}})


def _runs_anything(scene: str) -> bool:
    return True


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


@pytest.mark.parametrize("name", [3, ["personal"]], ids=["int", "list"])
def test_scope_by_name_raises_value_error_for_a_scope_that_is_not_a_string(name):
    with pytest.raises(ValueError):
        scope_by_name(name)


# ---------------------------------------------------------------------------
# LobbyConfig — built from the lobby pack's Settings
# ---------------------------------------------------------------------------


def test_config_resolves_scopes_and_entries_in_order():
    settings = _lobby_settings(
        ["personal", "global.main"],
        [
            {"scene": "hardware_test", "effect": "elements.fire", "options": {"level": 5}},
            {"scene": "tag", "effect": "elements.ice", "options": {"level": 3}},
        ],
    )

    config = LobbyConfig(settings, _runs_anything)

    assert config.scopes == [Scope.PERSONAL, Scope.Global.MAIN]
    assert [e.scene for e in config.entries] == ["hardware_test", "tag"]
    assert [e.effect for e in config.entries] == ["elements.fire", "elements.ice"]
    assert config.entries[0].options == {"level": 5}


def test_config_defaults_missing_options_to_empty_dict():
    settings = _lobby_settings(
        ["personal"], [{"scene": "hardware_test", "effect": "elements.fire"}]
    )

    config = LobbyConfig(settings, _runs_anything)

    assert config.entries[0].options == {}


def test_config_raises_on_empty_scopes():
    settings = _lobby_settings([], [{"scene": "hardware_test", "effect": "elements.fire"}])

    with pytest.raises(ValueError, match="scopes"):
        LobbyConfig(settings, _runs_anything)


def test_config_raises_on_empty_entries():
    settings = _lobby_settings(["personal"], [])

    with pytest.raises(ValueError, match="entries"):
        LobbyConfig(settings, _runs_anything)


def test_config_raises_on_unknown_scope_name():
    settings = _lobby_settings(
        ["not-a-real-scope"], [{"scene": "hardware_test", "effect": "elements.fire"}]
    )

    with pytest.raises(ValueError, match="not-a-real-scope"):
        LobbyConfig(settings, _runs_anything)


def test_config_raises_on_entry_missing_scene():
    settings = _lobby_settings(["personal"], [{"effect": "elements.fire"}])

    with pytest.raises(ValueError, match="scene"):
        LobbyConfig(settings, _runs_anything)


def test_config_raises_on_entry_missing_effect():
    settings = _lobby_settings(["personal"], [{"scene": "hardware_test"}])

    with pytest.raises(ValueError, match="effect"):
        LobbyConfig(settings, _runs_anything)


def test_config_raises_on_an_entry_that_is_not_an_object():
    settings = _lobby_settings(["personal"], ["hardware_test"])

    with pytest.raises(ValueError, match="hardware_test"):
        LobbyConfig(settings, _runs_anything)


_THREE_ENTRIES = [
    {"scene": "hardware_test", "effect": "elements.lightning"},
    {"scene": "red_light_green_light", "effect": "elements.fire"},
    {"scene": "tag", "effect": "basic.solid"},
]


def test_config_leaves_out_entries_the_device_cannot_run_keeping_the_order():
    settings = _lobby_settings(["personal"], _THREE_ENTRIES)

    config = LobbyConfig(settings, lambda scene: scene != "red_light_green_light")

    assert [e.scene for e in config.entries] == ["hardware_test", "tag"]


def test_config_raises_when_the_device_can_run_no_entry():
    settings = _lobby_settings(["personal"], _THREE_ENTRIES)

    with pytest.raises(ValueError, match="entries"):
        LobbyConfig(settings, lambda scene: False)


def test_config_checks_every_entry_before_asking_whether_the_device_can_run_it():
    settings = _lobby_settings(["personal"], [*_THREE_ENTRIES, {"scene": "tag"}])

    with pytest.raises(ValueError, match="effect"):
        LobbyConfig(settings, lambda scene: False)

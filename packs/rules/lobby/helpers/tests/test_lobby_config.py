"""Tests for ``LobbyConfig``, ``LobbyEntry``, and the lobby-local ``scope_by_name`` resolver."""

from __future__ import annotations

import pytest

from engine.settings import Settings
from engine.state import Scope
from packs.rules.lobby.helpers.lobby_config import LobbyConfig, LobbyEntry, scope_by_name
from packs.tests.settings_helper import settings_for


def _lobby_settings(scopes: list, entries: list) -> Settings:
    return settings_for(rule_packs={"lobby": {"scopes": scopes, "entries": entries}})


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
# LobbyConfig.from_settings
# ---------------------------------------------------------------------------


def test_from_settings_resolves_scopes_and_entries_in_order():
    settings = _lobby_settings(
        ["personal", "global.main"],
        [
            {"scene": "hardware_test", "effect": "elements.fire", "options": {"level": 5}},
            {"scene": "tag", "effect": "elements.ice", "options": {"level": 3}},
        ],
    )

    config = LobbyConfig.from_settings(settings)

    assert config.scopes == [Scope.PERSONAL, Scope.Global.MAIN]
    assert [e.scene for e in config.entries] == ["hardware_test", "tag"]
    assert [e.effect for e in config.entries] == ["elements.fire", "elements.ice"]
    assert config.entries[0].options == {"level": 5}


def test_from_settings_defaults_missing_options_to_empty_dict():
    settings = _lobby_settings(
        ["personal"], [{"scene": "hardware_test", "effect": "elements.fire"}]
    )

    config = LobbyConfig.from_settings(settings)

    assert config.entries[0].options == {}


def test_from_settings_raises_on_empty_scopes():
    settings = _lobby_settings([], [{"scene": "hardware_test", "effect": "elements.fire"}])

    with pytest.raises(ValueError, match="scopes"):
        LobbyConfig.from_settings(settings)


def test_from_settings_raises_on_empty_entries():
    settings = _lobby_settings(["personal"], [])

    with pytest.raises(ValueError, match="entries"):
        LobbyConfig.from_settings(settings)


def test_from_settings_raises_on_unknown_scope_name():
    settings = _lobby_settings(
        ["not-a-real-scope"], [{"scene": "hardware_test", "effect": "elements.fire"}]
    )

    with pytest.raises(ValueError, match="not-a-real-scope"):
        LobbyConfig.from_settings(settings)


def test_from_settings_raises_on_entry_missing_scene():
    settings = _lobby_settings(["personal"], [{"effect": "elements.fire"}])

    with pytest.raises(ValueError, match="scene"):
        LobbyConfig.from_settings(settings)


def test_from_settings_raises_on_entry_missing_effect():
    settings = _lobby_settings(["personal"], [{"scene": "hardware_test"}])

    with pytest.raises(ValueError, match="effect"):
        LobbyConfig.from_settings(settings)


def test_from_settings_raises_on_an_entry_that_is_not_an_object():
    settings = _lobby_settings(["personal"], ["hardware_test"])

    with pytest.raises(ValueError, match="hardware_test"):
        LobbyConfig.from_settings(settings)

"""Tests for the read-only Settings view rules read through ``GameState.settings``."""

from __future__ import annotations

import pytest

from engine.settings import Settings, UnknownSettingError
from engine.state import EffectControls, GameState, SceneControls


def test_a_declared_setting_reads_by_namespace_and_name() -> None:
    settings = Settings({"return_to_lobby": {"hold_seconds": 2.5}})

    assert settings.get("return_to_lobby", "hold_seconds") == 2.5


@pytest.mark.parametrize(
    ("namespace", "name"),
    [("return_to_lobby", "hold_secs"), ("lobby", "hold_seconds")],
)
def test_reading_an_undeclared_setting_raises_naming_it(namespace: str, name: str) -> None:
    settings = Settings({"return_to_lobby": {"hold_seconds": 2.5}})

    with pytest.raises(UnknownSettingError) as excinfo:
        settings.get(namespace, name)

    assert (excinfo.value.namespace, excinfo.value.name) == (namespace, name)


def test_the_view_has_no_write_path() -> None:
    settings = Settings({"return_to_lobby": {"hold_seconds": 2.5}})

    assert not any(attr.startswith(("set", "update", "pop")) for attr in dir(settings))
    with pytest.raises(AttributeError):
        settings.hold_seconds = 1.0  # type: ignore[attr-defined]


def test_changing_the_source_mapping_does_not_change_the_view() -> None:
    values = {"return_to_lobby": {"hold_seconds": 2.5}}
    settings = Settings(values)

    values["return_to_lobby"]["hold_seconds"] = 9.0

    assert settings.get("return_to_lobby", "hold_seconds") == 2.5


def test_game_state_exposes_the_settings_it_was_given() -> None:
    settings = Settings({"return_to_lobby": {"hold_seconds": 2.5}})
    state = GameState(EffectControls(), SceneControls(), settings=settings)

    assert state.settings.get("return_to_lobby", "hold_seconds") == 2.5


def test_a_settings_value_is_not_in_the_game_data_store() -> None:
    state = GameState(
        EffectControls(), SceneControls(), settings=Settings({"scene": {"max_ammo": 3}})
    )

    assert not state.has("max_ammo")


def test_a_game_state_built_without_settings_declares_none() -> None:
    state = GameState(EffectControls(), SceneControls())

    with pytest.raises(UnknownSettingError):
        state.settings.get("return_to_lobby", "hold_seconds")

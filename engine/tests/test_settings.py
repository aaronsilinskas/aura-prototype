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


def test_assigning_an_attribute_on_the_view_raises() -> None:
    settings = Settings({"return_to_lobby": {"hold_seconds": 2.5}})

    with pytest.raises(AttributeError):
        settings.hold_seconds = 1.0  # type: ignore[attr-defined]


def test_assigning_an_item_on_the_view_raises() -> None:
    settings = Settings({"return_to_lobby": {"hold_seconds": 2.5}})

    with pytest.raises(TypeError):
        settings["return_to_lobby"] = {"hold_seconds": 1.0}  # type: ignore[index]


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


@pytest.mark.parametrize(
    ("getter", "value"),
    [
        ("get_int", 3),
        ("get_float", 2.5),
        ("get_bool", True),
        ("get_str", "red"),
        ("get_list", [1, 2]),
    ],
)
def test_a_typed_read_returns_a_setting_of_that_type(getter: str, value: object) -> None:
    settings = Settings({"scene": {"max_ammo": value}})

    assert getattr(settings, getter)("scene", "max_ammo") == value


def test_a_float_read_of_an_int_setting_returns_it_as_a_float() -> None:
    value = Settings({"scene": {"max_ammo": 3}}).get_float("scene", "max_ammo")

    assert (value, type(value)) == (3.0, float)


@pytest.mark.parametrize(
    ("getter", "value"),
    [
        ("get_int", 2.5),
        ("get_int", True),
        ("get_float", False),
        ("get_bool", 1),
        ("get_str", 3),
        ("get_list", "a, b"),
    ],
)
def test_a_typed_read_of_a_setting_of_another_type_raises_type_error(
    getter: str, value: object
) -> None:
    settings = Settings({"scene": {"max_ammo": value}})

    with pytest.raises(TypeError):
        getattr(settings, getter)("scene", "max_ammo")


def test_a_typed_read_of_an_undeclared_setting_raises_unknown_setting_error() -> None:
    with pytest.raises(UnknownSettingError):
        Settings().get_float("scene", "max_ammo")


def test_changing_a_list_read_does_not_change_the_next_read() -> None:
    settings = Settings({"lobby": {"scopes": ["personal"]}})

    settings.get_list("lobby", "scopes").append("ambient")

    assert settings.get_list("lobby", "scopes") == ["personal"]

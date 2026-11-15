"""Every Scene Config reads each of its scene's declared Settings into the field of the same name.

One check for every scene under ``packs/scenes/`` that declares scene Settings:
the scene's Scene Config is found through its ``StateSlot`` accessor, and each
declared Setting, overridden alone to a distinct value, must land in the config
field of the same name. A declared Setting with no such field fails, whether no
field reads it (a dead Setting) or the field that reads it is spelled
differently. Scene-specific config logic (derived values, cross-Setting checks)
stays tested beside each config.

It covers only same-name Scene Configs. The lobby Rule pack's config is left
out: its fields hold scopes and entries derived from its Settings, not the
Settings' values, and it needs a can-run check to build, so "the field holds
the override" doesn't apply to it.

Reflection is fine here: tests never ship to a device, and the configs keep
their explicit one-line reads (ADR-0010).
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import get_type_hints

import pytest

from engine.settings import Settings
from engine.state import EffectControls, GameState, SceneControls, StateSlot
from packs.tests.settings_helper import (
    declared_scene_settings,
    scenes_declaring_settings,
    settings_for,
)


def _builds_from_settings(cls: type) -> bool:
    init = vars(cls).get("__init__")
    if init is None:
        return False
    hints = get_type_hints(init)
    hints.pop("return", None)
    return hints == {"settings": Settings}


def _scene_config_slot(scene: str) -> StateSlot:
    """Return the one ``StateSlot`` in *scene*'s rules whose class is built from Settings alone."""
    package = importlib.import_module(f"packs.scenes.{scene}.rules")
    slots: dict[int, StateSlot] = {}
    for module_info in pkgutil.walk_packages(package.__path__, f"{package.__name__}."):
        if ".tests" in module_info.name:
            continue
        module = importlib.import_module(module_info.name)
        for value in vars(module).values():
            if isinstance(value, StateSlot) and _builds_from_settings(value._expected_class):
                slots[id(value)] = value
    if len(slots) != 1:
        pytest.fail(
            f"scene {scene!r} declares Settings but its rules have {len(slots)} Scene Config"
            + " StateSlots, not one"
        )
    return next(iter(slots.values()))


def _distinct_override(declaration: dict[str, object], taken: set[object]) -> object:
    """Return a valid value for *declaration* that differs from every value in *taken*."""
    type_name = declaration["type"]
    default = declaration.get("default")
    if type_name == "bool":
        return not default
    if type_name == "str":
        return f"{default}-override"
    if type_name not in ("int", "float"):
        pytest.fail(f"no distinct override rule for a {type_name} Setting")
    step = 1 if type_name == "int" else 0.01
    candidate = default if isinstance(default, (int, float)) else 0
    while True:
        candidate += step
        if candidate not in taken:
            return candidate


_SCENE_SETTINGS = [
    (scene, setting)
    for scene in scenes_declaring_settings()
    for setting in declared_scene_settings(scene)
]


@pytest.mark.parametrize(("scene", "setting"), _SCENE_SETTINGS)
def test_each_declared_scene_setting_override_lands_in_the_scene_config_field_of_the_same_name(
    scene, setting
):
    declarations = declared_scene_settings(scene)
    defaults = {declaration.get("default") for declaration in declarations.values()}
    override = _distinct_override(declarations[setting], defaults)
    settings = settings_for(scene, settings={setting: override})
    state = GameState(EffectControls(), SceneControls(), settings=settings)

    config = _scene_config_slot(scene)(state)

    if not hasattr(config, setting):
        pytest.fail(
            f"scene {scene!r} declares Setting {setting!r} but {type(config).__name__}"
            + " has no field of that name"
        )
    assert getattr(config, setting) == override, (
        f"scene {scene!r}: {type(config).__name__}.{setting} does not hold the Setting's override"
    )

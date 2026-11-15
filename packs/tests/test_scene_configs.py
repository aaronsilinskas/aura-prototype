"""Every Scene Config reads each of its scene's declared Settings into the field of the same name.

One check for every scene under ``packs/scenes/`` that declares scene Settings:
the scene's Scene Config is found by calling its ``StateSlot`` accessors, and each
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

import functools
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


@functools.cache
def _scene_state_slots(scene: str) -> tuple[StateSlot, ...]:
    """Return every ``StateSlot`` defined in *scene*'s rules package, each once."""
    package = importlib.import_module(f"packs.scenes.{scene}.rules")
    slots: dict[int, StateSlot] = {}
    for module_info in pkgutil.walk_packages(package.__path__, f"{package.__name__}."):
        if ".tests" in module_info.name:
            continue
        module = importlib.import_module(module_info.name)
        for value in vars(module).values():
            if isinstance(value, StateSlot):
                slots[id(value)] = value
    return tuple(slots.values())


def _scene_config(scene: str, state: GameState) -> object:
    """Return the one value from *scene*'s slots whose class builds from Settings alone."""
    configs = [
        value
        for value in (slot(state) for slot in _scene_state_slots(scene))
        if _builds_from_settings(type(value))
    ]
    if len(configs) != 1:
        pytest.fail(
            f"scene {scene!r} declares Settings but its rules have {len(configs)} Scene Config"
            + " StateSlots, not one"
        )
    return configs[0]


def _distinct_override(declaration: dict[str, object], taken: set[object]) -> object:
    """Return a valid value for *declaration* that differs from every value in *taken*."""
    type_name = declaration["type"]
    if type_name not in ("int", "float"):
        pytest.fail(f"no distinct override rule for a {type_name} Setting")
    default = declaration.get("default")
    step = 1 if type_name == "int" else 0.01
    candidate = default if isinstance(default, (int, float)) else 0
    while True:
        candidate += step
        if candidate not in taken:
            return candidate


class _NoSuchField:
    def __repr__(self) -> str:
        return "<no field of that name>"


_NO_SUCH_FIELD = _NoSuchField()


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

    config = _scene_config(scene, state)

    assert getattr(config, setting, _NO_SUCH_FIELD) == override, (
        f"scene {scene!r} declares Setting {setting!r} but {type(config).__name__}.{setting}"
        + " does not hold its override"
    )

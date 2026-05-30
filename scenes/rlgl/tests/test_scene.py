from __future__ import annotations

from unittest.mock import MagicMock

from engine.scene import Scene
from engine.state import EffectControls, Scope


def test_factory_returns_scene():
    from scenes.rlgl.scene import factory

    scene = factory()
    assert isinstance(scene, Scene)


def test_factory_includes_effect_packs():
    from scenes.rlgl.scene import factory

    scene = factory()
    assert ("elements", "1.0") in scene.effect_packs
    assert ("basic", "1.1") in scene.effect_packs


def test_factory_includes_rlgl_effect_pack():
    from scenes.rlgl.scene import factory

    scene = factory()
    assert ("rlgl", "1.0") in scene.effect_packs


def test_factory_includes_rlgl_rule_pack():
    from scenes.rlgl.scene import factory

    scene = factory()
    assert ("rlgl", "1.0") in scene.rule_packs


def test_factory_no_initial_data_by_default():
    from scenes.rlgl.scene import factory

    scene = factory()
    assert scene.initial_data is None


def test_on_unload_stops_all_effects():
    from scenes.rlgl.scene import factory

    scene = factory()
    ec = MagicMock(spec=EffectControls)
    scene.on_unload(ec)
    ec.stop_effect.assert_called_once_with(Scope.ALL)

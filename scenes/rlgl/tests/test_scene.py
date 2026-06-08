from __future__ import annotations

from engine.scene import Scene


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

"""Behaviour-driven tests for app/scene_composition.py."""

from app.scene_composition import build_scene_runtime
from engine.state import Scope
from hardware.shared.device_hardware import DeviceHardware


def _fake_hw() -> DeviceHardware:
    """Return a DeviceHardware built entirely from CPython-safe fakes."""
    return DeviceHardware(
        outputs=[],
        buttons="fake-buttons",
        accelerometer=None,
        network_controls="fake-network-controls",
        transmit_pump="fake-transmit-pump",
        ir_receiver=None,
    )


def test_known_scene_name_activates_that_scenes_local_effects():
    """The tag scene's scene-local 'ready' effect resolves once tag is active."""
    runtime = build_scene_runtime(_fake_hw(), "tag")

    receipt = runtime.effect_manager.set_effect(Scope.PERSONAL, "scene.ready", {})

    assert receipt is not None


def test_unknown_scene_name_falls_back_to_hardware_test():
    """An unregistered scene name falls back to hardware_test's scene-local effects."""
    runtime = build_scene_runtime(_fake_hw(), "not-a-real-scene")

    receipt = runtime.effect_manager.set_effect(Scope.PERSONAL, "scene.sfx_test", {})

    assert receipt is not None

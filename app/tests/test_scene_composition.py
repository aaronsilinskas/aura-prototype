"""Behaviour-driven tests for app/scene_composition.py."""

from app.scene_composition import build_scene_runtime
from engine.network import TransmitPump
from engine.state import Scope
from hardware.shared.device_hardware import DeviceHardware
from hardware.shared.ir_manager import InfraredManager
from hardware.shared.ir_transport import InfraredReceiver


def _fake_hw(transmit_pump=None, ir_receiver=None) -> DeviceHardware:
    """Return a DeviceHardware built entirely from CPython-safe fakes."""
    return DeviceHardware(
        outputs=[],
        buttons="fake-buttons",
        accelerometer=None,
        network_controls="fake-network-controls",
        transmit_pump=transmit_pump if transmit_pump is not None else "fake-transmit-pump",
        ir_receiver=ir_receiver,
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


# ---------------------------------------------------------------------------
# SceneRuntime.ir wiring (issue #654)
# ---------------------------------------------------------------------------


class _RecordingTransmitPump(TransmitPump):
    """Records how many times poll_transmits() was called."""

    def __init__(self) -> None:
        self.poll_calls = 0

    def poll_transmits(self) -> dict:
        self.poll_calls += 1
        return {}


class _StubReceiver(InfraredReceiver):
    """Returns a fixed payload from every receive() call."""

    def __init__(self, payload: bytearray) -> None:
        super().__init__()
        self._payload = payload

    def receive(self) -> bytearray | None:
        return self._payload


def test_build_scene_runtime_exposes_an_infrared_manager_as_ir():
    runtime = build_scene_runtime(_fake_hw(), "tag")

    assert isinstance(runtime.ir, InfraredManager)


def test_build_scene_runtime_wires_ir_to_the_hardware_bundles_transmit_pump():
    """runtime.ir.update() must drive hw.transmit_pump, not a copy of it."""
    pump = _RecordingTransmitPump()
    runtime = build_scene_runtime(_fake_hw(transmit_pump=pump), "tag")

    runtime.ir.update()

    assert pump.poll_calls == 1


def test_build_scene_runtime_wires_ir_to_the_hardware_bundles_ir_receiver():
    """runtime.ir.update() must drive hw.ir_receiver, surfacing its packet as received."""
    payload = bytearray(b"\x01")
    runtime = build_scene_runtime(
        _fake_hw(transmit_pump=_RecordingTransmitPump(), ir_receiver=_StubReceiver(payload)),
        "tag",
    )

    runtime.ir.update()

    assert runtime.ir.received is payload

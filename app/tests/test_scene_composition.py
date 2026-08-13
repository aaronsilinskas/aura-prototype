"""Behaviour-driven tests for app/scene_composition.py."""

import pytest

from app.scene_composition import build_scene_runtime
from engine.audio import AudioRegistry
from engine.network import TransmitPump
from engine.state import Scope
from hardware.shared.device_hardware import DeviceHardware
from hardware.shared.ir_manager import InfraredManager
from hardware.shared.ir_transport import InfraredReceiver
from hardware.shared.radio_manager import RadioManager
from hardware.shared.radio_transport import RadioTransport


def _fake_hw(
    transmit_pump=None, ir_receiver=None, radio=None, audio_registry=None
) -> DeviceHardware:
    """Return a DeviceHardware built entirely from CPython-safe fakes."""
    return DeviceHardware(
        outputs=[],
        buttons="fake-buttons",
        accelerometer=None,
        network_controls="fake-network-controls",
        transmit_pump=transmit_pump if transmit_pump is not None else "fake-transmit-pump",
        ir_receiver=ir_receiver,
        radio=radio,
        storage=None,
        audio_registry=audio_registry,
    )


def test_known_scene_name_activates_that_scenes_local_effects():
    """The tag scene's scene-local 'ready' effect resolves once tag is active."""
    runtime = build_scene_runtime(_fake_hw(), "tag")

    receipt = runtime.effect_manager.set_effect(Scope.PERSONAL, "scene.ready", {})

    assert receipt is not None


def test_unknown_scene_name_raises_naming_the_known_scenes():
    """An unregistered scene name fails loudly instead of falling back to hardware_test."""
    with pytest.raises(ValueError, match="hardware_test"):
        build_scene_runtime(_fake_hw(), "not-a-real-scene")


# ---------------------------------------------------------------------------
# SceneRuntime.ir wiring (issue #654)
# ---------------------------------------------------------------------------


class _CountingTransmitPump(TransmitPump):
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
    pump = _CountingTransmitPump()
    runtime = build_scene_runtime(_fake_hw(transmit_pump=pump), "tag")

    runtime.ir.update()

    assert pump.poll_calls == 1


def test_build_scene_runtime_wires_ir_to_the_hardware_bundles_ir_receiver():
    """runtime.ir.update() must drive hw.ir_receiver, surfacing its packet as received."""
    payload = bytearray(b"\x01")
    runtime = build_scene_runtime(
        _fake_hw(transmit_pump=_CountingTransmitPump(), ir_receiver=_StubReceiver(payload)),
        "tag",
    )

    runtime.ir.update()

    assert runtime.ir.received is payload


# ---------------------------------------------------------------------------
# SceneRuntime.radio wiring (issue #704)
# ---------------------------------------------------------------------------


class _StubRadioTransport(RadioTransport):
    """Returns a fixed (from_byte, data) pair from every receive() call."""

    def __init__(self, from_byte: int, data: bytes) -> None:
        self._packet = (from_byte, data)

    def send(self, data: bytes) -> None:
        pass  # unused by these tests

    def receive(self) -> "tuple[int, bytes] | None":
        return self._packet


def test_build_scene_runtime_exposes_a_radio_manager_as_radio():
    runtime = build_scene_runtime(_fake_hw(), "tag")

    assert isinstance(runtime.radio, RadioManager)


def test_build_scene_runtime_wires_radio_to_the_hardware_bundles_radio_transport():
    """runtime.radio.update() must drive hw.radio, surfacing its packet as received."""
    runtime = build_scene_runtime(
        _fake_hw(radio=_StubRadioTransport(3, b"\xab\xcd")),
        "tag",
    )

    runtime.radio.update()

    assert runtime.radio.received.data == b"\xab\xcd"
    assert runtime.radio.received.sender == "3"


# ---------------------------------------------------------------------------
# Audio registry wiring: base scan + scene overlay (issue #804)
# ---------------------------------------------------------------------------


def test_build_scene_runtime_scans_effect_pack_sounds_into_the_devices_audio_registry():
    """packs/effects/*/sounds is scanned into hw.audio_registry's base, qualified
    by pack name, so basic.game_over_sting_start resolves once the runtime is built."""
    hw = _fake_hw(audio_registry=AudioRegistry())

    build_scene_runtime(hw, "hardware_test")

    assert (
        hw.audio_registry.path("basic.game_over_sting_start")
        == "packs/effects/basic/sounds/game_over_sting_start.wav"
    )
    assert (
        hw.audio_registry.path("elements.lightning_strike")
        == "packs/effects/elements/sounds/lightning_strike.wav"
    )


def test_build_scene_runtime_installs_hardware_test_scenes_sounds_as_the_active_overlay():
    """Activating hardware_test installs its sounds/ folder as the AudioRegistry
    overlay, so scene.sfx_test_start -- the clip sfx_test's audio references --
    resolves through the same registry AudioEffectOutput would use on real hardware."""
    hw = _fake_hw(audio_registry=AudioRegistry())

    build_scene_runtime(hw, "hardware_test")

    assert (
        hw.audio_registry.path("scene.sfx_test_start")
        == "packs/scenes/hardware_test/sounds/sfx_test_start.wav"
    )


def test_build_scene_runtime_with_no_audio_registry_skips_scan_and_still_activates_scene():
    """A device with no enabled audio section (hw.audio_registry is None) gets no
    base scan and no overlay wiring, but scene activation is otherwise unaffected."""
    hw = _fake_hw()

    runtime = build_scene_runtime(hw, "hardware_test")

    assert hw.audio_registry is None
    receipt = runtime.effect_manager.set_effect(Scope.PERSONAL, "scene.sfx_test", {})
    assert receipt is not None

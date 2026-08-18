"""Behaviour-driven tests for app/scene_composition.py."""

import pytest

from app.scene_composition import build_scene_runtime, resolve_ir_codec
from engine.audio import AudioRegistry
from engine.network import TransmitPump
from engine.scene import Scene, SceneRegistry
from engine.state import Scope
from hardware.shared.device_hardware import DeviceHardware
from hardware.shared.ir_codecs.aura import AuraInfraredDecoder, AuraInfraredEncoder
from hardware.shared.ir_codecs.tag import TagInfraredDecoder, TagInfraredEncoder
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
        magnetometer=None,
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
# resolve_ir_codec (issue #862)
# ---------------------------------------------------------------------------


def test_resolve_ir_codec_returns_the_aura_pair_for_a_scene_with_no_declared_codec():
    """A scene with no ir_codec key defaults to the Aura wire-frame codec."""
    scene_registry = SceneRegistry()
    scene_registry.register("no_codec", lambda: Scene(effect_packs=[], rule_packs=[]))

    encoder, decoder = resolve_ir_codec(scene_registry, "no_codec")

    assert isinstance(encoder, AuraInfraredEncoder)
    assert isinstance(decoder, AuraInfraredDecoder)


def test_resolve_ir_codec_returns_the_tag_pair_for_a_scene_declaring_the_tag_codec():
    """A scene declaring ir_codec: 'tag' resolves to the Tag protocol codec."""
    scene_registry = SceneRegistry()
    scene_registry.register(
        "tag_codec", lambda: Scene(effect_packs=[], rule_packs=[], ir_codec="tag")
    )

    encoder, decoder = resolve_ir_codec(scene_registry, "tag_codec")

    assert isinstance(encoder, TagInfraredEncoder)
    assert isinstance(decoder, TagInfraredDecoder)


def test_resolve_ir_codec_raises_unknown_codec_error_for_an_undeclared_codec_name():
    """A scene declaring a codec name with no matching hardware.shared.ir_codecs module
    fails loudly by codec name, distinct from an unknown *scene* name."""
    scene_registry = SceneRegistry()
    scene_registry.register(
        "bogus_codec", lambda: Scene(effect_packs=[], rule_packs=[], ir_codec="tv_remote")
    )

    with pytest.raises(ValueError, match="tv_remote"):
        resolve_ir_codec(scene_registry, "bogus_codec")


# ---------------------------------------------------------------------------
# build_scene_runtime — optional pre-built scene_registry (issue #862)
# ---------------------------------------------------------------------------


def test_build_scene_runtime_activates_a_scene_only_registered_in_the_supplied_scene_registry():
    """A pre-built, already-scanned registry is used as-is instead of a fresh internal
    scan -- this scene exists nowhere under packs/scenes, only in the registry passed in."""
    scene_registry = SceneRegistry()
    scene_registry.register(
        "only_in_supplied_registry", lambda: Scene(effect_packs=[], rule_packs=[])
    )

    runtime = build_scene_runtime(
        _fake_hw(), "only_in_supplied_registry", scene_registry=scene_registry
    )

    assert runtime.manager.active_state is not None


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


# ---------------------------------------------------------------------------
# Audio registry wiring: tag scene discovery (issue #805)
# ---------------------------------------------------------------------------


def test_build_scene_runtime_installs_tag_scenes_sounds_as_the_active_overlay():
    """Activating tag installs its sounds/ folder as the AudioRegistry overlay, so
    every scene.<stem> clip a tag effect references resolves through the same
    registry AudioEffectOutput would use on real hardware."""
    hw = _fake_hw(audio_registry=AudioRegistry())

    build_scene_runtime(hw, "tag")

    for stem in (
        "fire_shot_start",
        "reload",
        "reload_complete",
        "dry_fire_start",
        "ready_shots_start",
        "go_start",
        "warning_pulse_peak",
        "hit_start",
    ):
        assert hw.audio_registry.path(f"scene.{stem}") == f"packs/scenes/tag/sounds/{stem}.wav"


def test_build_scene_runtime_resolves_tags_shared_game_over_sting_via_the_basic_pack():
    """tag's game_over_sting effect points at basic's shared clip rather than its
    own -- it must resolve from the base scan, not from tag's sounds/ overlay."""
    hw = _fake_hw(audio_registry=AudioRegistry())

    build_scene_runtime(hw, "tag")

    assert (
        hw.audio_registry.path("basic.game_over_sting_start")
        == "packs/effects/basic/sounds/game_over_sting_start.wav"
    )


# ---------------------------------------------------------------------------
# Audio registry wiring: red_light_green_light scene discovery (issue #806)
# ---------------------------------------------------------------------------


def test_build_scene_runtime_installs_rlgls_sounds_as_the_active_overlay():
    """Activating red_light_green_light installs its sounds/ folder as the
    AudioRegistry overlay, so every scene.<stem> clip an rlgl effect references
    resolves through the same registry AudioEffectOutput would use on real
    hardware."""
    hw = _fake_hw(audio_registry=AudioRegistry())

    build_scene_runtime(hw, "red_light_green_light")

    for stem in (
        "green_light_music_start",
        "red_light_music_start",
        "level_up_start",
        "win_sting_start",
        "ready_start",
        "warning_sting_peak",
    ):
        assert (
            hw.audio_registry.path(f"scene.{stem}")
            == f"packs/scenes/red_light_green_light/sounds/{stem}.wav"
        )


def test_build_scene_runtime_resolves_rlgls_shared_game_over_sting_via_the_basic_pack():
    """rlgl's game_over_sting effect points at basic's shared clip rather than its
    own -- it must resolve from the base scan, not from rlgl's sounds/ overlay."""
    hw = _fake_hw(audio_registry=AudioRegistry())

    build_scene_runtime(hw, "red_light_green_light")

    assert (
        hw.audio_registry.path("basic.game_over_sting_start")
        == "packs/effects/basic/sounds/game_over_sting_start.wav"
    )

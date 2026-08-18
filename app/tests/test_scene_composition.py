"""Behaviour-driven tests for app/scene_composition.py."""

import json
import sys
from pathlib import Path

import pytest

from app.scene_composition import build_scene_runtime, resolve_ir_codec
from engine.audio import AudioRegistry
from engine.events import Event, EventGroup
from engine.network import TransmitPump
from engine.scene import Scene, SceneRegistry
from engine.state import Scope
from hardware.shared.device_hardware import DeviceHardware
from hardware.shared.device_storage import DeviceStorage
from hardware.shared.ir_codecs.aura import AuraInfraredDecoder, AuraInfraredEncoder
from hardware.shared.ir_codecs.tag import TagInfraredDecoder, TagInfraredEncoder
from hardware.shared.ir_manager import InfraredManager
from hardware.shared.ir_transport import InfraredReceiver
from hardware.shared.radio_manager import RadioManager
from hardware.shared.radio_transport import RadioTransport


def _fake_hw(
    transmit_pump=None, ir_receiver=None, radio=None, audio_registry=None, storage=None
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
        storage=storage,
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


def test_resolve_ir_codec_returns_the_tag_pair_for_the_real_tag_scene():
    """The real tag scene's scene.json declares ir_codec: 'tag' (issue #863), so
    scene_demo running "scene": "tag" gets the Tag protocol codec end to end
    instead of the Aura default every other scene gets."""
    scene_registry = SceneRegistry()
    scene_registry.scan_dir("packs/scenes", "packs.scenes")

    encoder, decoder = resolve_ir_codec(scene_registry, "tag")

    assert isinstance(encoder, TagInfraredEncoder)
    assert isinstance(decoder, TagInfraredDecoder)


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


# ---------------------------------------------------------------------------
# Card scenes: aura_packs/scenes discovery (issue #870)
# ---------------------------------------------------------------------------

_CARD_TEST_EVENT_GROUP = EventGroup("card_scene_test")

_CARD_RULE_SOURCE = """\
from engine.engine import GameRule
from engine.events import Event
from engine.state import GameState


class _CardRule(GameRule):
    def __init__(self) -> None:
        self.on(Event, self._handle)

    def _handle(self, event: Event, state: GameState) -> None:
        state.set("card_rule_ran", True)


RULE = _CardRule()
"""

_CARD_EFFECT_SOURCE = """\
from effects.effect import AudioPlaybackConfig, Effect, EffectAudio, EffectConfig
from engine.effects.manager import EffectBuilder

_AUDIO = EffectAudio(clips={"start": AudioPlaybackConfig(name="scene.card_clip", loop=False)})


class _Builder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        return Effect(name=name, pixels=None, audio=_AUDIO)


BUILD = _Builder()
"""


def _write_scene_json(path, data: dict) -> None:
    (path / "scene.json").write_text(json.dumps(data))


def _minimal_scene_json(**overrides) -> dict:
    base = {"version": "1.0", "effect_packs": [], "rule_packs": []}
    base.update(overrides)
    return base


def _make_card_scene(mount_root: Path, scene_name: str, **json_overrides) -> Path:
    """Create aura_packs/scenes/<scene_name>/ under *mount_root*.

    Supplies an empty __init__.py at every package level, mirroring the
    layout the flash packs/ tree already has. Returns the scene directory.
    """
    aura_packs = mount_root / "aura_packs"
    scenes = aura_packs / "scenes"
    scene_dir = scenes / scene_name
    scene_dir.mkdir(parents=True, exist_ok=True)
    (aura_packs / "__init__.py").touch()
    (scenes / "__init__.py").touch()
    (scene_dir / "__init__.py").touch()
    _write_scene_json(scene_dir, _minimal_scene_json(**json_overrides))
    return scene_dir


def _add_card_scene_rule(scene_dir, item_name: str, content: str) -> None:
    rules_dir = scene_dir / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    (rules_dir / "__init__.py").touch()
    (rules_dir / f"{item_name}.py").write_text(content)


def _add_card_scene_effect(scene_dir, item_name: str, content: str) -> None:
    effects_dir = scene_dir / "effects"
    effects_dir.mkdir(parents=True, exist_ok=True)
    (effects_dir / "__init__.py").touch()
    (effects_dir / f"{item_name}.py").write_text(content)


def _add_card_scene_sound(scene_dir, stem: str) -> None:
    sounds_dir = scene_dir / "sounds"
    sounds_dir.mkdir(parents=True, exist_ok=True)
    (sounds_dir / f"{stem}.wav").write_bytes(b"RIFF")  # contents unused; only the path matters


@pytest.fixture()
def card_storage(tmp_path):
    """Yield a real temp-directory DeviceStorage; clean up sys.path/sys.modules after.

    A real DeviceStorage (not FakeDeviceStorage) is required here, mirroring
    hardware/shared/tests/test_device_storage.py's precedent, because the
    behaviour under test is the module import off a real filesystem path
    build_scene_runtime adds to sys.path.
    """
    storage = DeviceStorage(str(tmp_path))
    known_modules = set(sys.modules)

    yield storage

    for key in list(sys.modules):
        if key not in known_modules:
            del sys.modules[key]
    if storage.mount_root in sys.path:
        sys.path.remove(storage.mount_root)


def test_build_scene_runtime_discovers_and_activates_a_card_scene(card_storage):
    """A scene that exists only under the card's aura_packs/scenes is selectable
    at boot -- it loads into the same SceneRegistry flash scenes populate."""
    _make_card_scene(Path(card_storage.mount_root), "card_scene")
    hw = _fake_hw(storage=card_storage)

    runtime = build_scene_runtime(hw, "card_scene")

    assert runtime.manager.active_state is not None


def test_card_scenes_local_rule_imports_off_the_card_and_handles_events(card_storage):
    """A card scene's scene-local rule is imported through the aura_packs. prefix
    against the card and receives events like any other scene-local rule."""
    scene_dir = _make_card_scene(Path(card_storage.mount_root), "card_scene")
    _add_card_scene_rule(scene_dir, "card_rule", _CARD_RULE_SOURCE)
    hw = _fake_hw(storage=card_storage)

    runtime = build_scene_runtime(hw, "card_scene")
    runtime.manager.active_state.queue_event(Event(_CARD_TEST_EVENT_GROUP, "ping"))
    runtime.manager.update()

    assert runtime.manager.active_state.get_or_none("card_rule_ran", bool) is True


def test_card_scenes_local_effect_imports_off_the_card_and_resolves_at_runtime(card_storage):
    """A card scene's scene-local effect is imported through the aura_packs. prefix
    and resolves via the same scene. prefix a flash scene-local effect uses."""
    scene_dir = _make_card_scene(Path(card_storage.mount_root), "card_scene")
    _add_card_scene_effect(scene_dir, "card_effect", _CARD_EFFECT_SOURCE)
    hw = _fake_hw(storage=card_storage)

    runtime = build_scene_runtime(hw, "card_scene")
    receipt = runtime.effect_manager.set_effect(Scope.PERSONAL, "scene.card_effect", {})

    assert receipt is not None


def test_card_scenes_bundled_sound_resolves_to_its_on_card_path(card_storage):
    """A card scene's sounds/ clip is recorded at its absolute on-card filesystem
    path -- resolved through the DeviceStorage port, never a re-derived '/sd' --
    and reaches the same AudioRegistry a flash scene's clip resolves through."""
    scene_dir = _make_card_scene(Path(card_storage.mount_root), "card_scene")
    _add_card_scene_sound(scene_dir, "card_clip")
    hw = _fake_hw(storage=card_storage, audio_registry=AudioRegistry())

    build_scene_runtime(hw, "card_scene")

    expected_path = str(scene_dir / "sounds" / "card_clip.wav")
    assert hw.audio_registry.path("scene.card_clip") == expected_path


def test_repeat_build_scene_runtime_calls_never_duplicate_the_mount_root_in_sys_path(
    card_storage,
):
    """The card's mount root is appended to sys.path once, even across repeated
    build_scene_runtime calls against the same storage -- the append is guarded,
    not just performed once per process by accident."""
    _make_card_scene(Path(card_storage.mount_root), "card_scene")
    hw = _fake_hw(storage=card_storage)

    build_scene_runtime(hw, "card_scene")
    build_scene_runtime(hw, "card_scene")

    assert sys.path.count(card_storage.mount_root) == 1


def test_device_with_no_storage_leaves_sys_path_unmutated():
    """No DeviceStorage means no card to scan -- sys.path is untouched and only
    flash scenes are ever discovered."""
    path_before = list(sys.path)

    build_scene_runtime(_fake_hw(), "tag")

    assert sys.path == path_before


def test_card_with_no_aura_packs_directory_leaves_sys_path_unmutated(card_storage):
    """Storage is present but the card carries no top-level aura_packs/ -- the
    sys.path append is gated on that directory's presence, not just on storage
    being non-None."""
    path_before = list(sys.path)
    hw = _fake_hw(storage=card_storage)

    build_scene_runtime(hw, "tag")

    assert sys.path == path_before


def test_card_with_no_aura_packs_directory_still_activates_a_flash_scene(card_storage):
    """Storage is present but the card carries no top-level aura_packs/ -- flash
    scene selection still works normally despite the (no-op) card scan."""
    hw = _fake_hw(storage=card_storage)

    runtime = build_scene_runtime(hw, "tag")

    assert runtime.manager.active_state is not None


def test_card_with_aura_packs_but_no_scenes_subdirectory_is_a_clean_no_op(card_storage):
    """aura_packs/ exists (so sys.path is still appended) but has no scenes/
    subdirectory to scan -- this must not raise, only skip the scan."""
    aura_packs = Path(card_storage.mount_root) / "aura_packs"
    aura_packs.mkdir(parents=True)
    (aura_packs / "__init__.py").touch()
    hw = _fake_hw(storage=card_storage)

    runtime = build_scene_runtime(hw, "tag")

    assert card_storage.mount_root in sys.path
    assert runtime.manager.active_state is not None


def test_card_scene_name_colliding_with_a_flash_scene_raises_at_scan_time(card_storage):
    """A card scene sharing a name with a flash scene is the existing cross-root
    collision SceneRegistry.scan_dir already enforces -- it must halt boot loudly
    rather than silently picking one source over the other."""
    _make_card_scene(Path(card_storage.mount_root), "tag")
    hw = _fake_hw(storage=card_storage)

    with pytest.raises(ValueError, match="tag"):
        build_scene_runtime(hw, "tag")


# ---------------------------------------------------------------------------
# Card rule packs: aura_packs/rules discovery (issue #872)
# ---------------------------------------------------------------------------

_CARD_RULE_PACK_SOURCE = """\
from engine.engine import GameRule
from engine.events import Event
from engine.state import GameState


class _CardPackRule(GameRule):
    def __init__(self) -> None:
        self.on(Event, self._handle)

    def _handle(self, event: Event, state: GameState) -> None:
        state.set("card_pack_rule_ran", True)


RULE = _CardPackRule()
"""


def _make_card_rule_pack(
    mount_root: Path, pack_name: str, item_name: str, content: str, version: str = "1.0"
) -> Path:
    """Create aura_packs/rules/<pack_name>/ under *mount_root* with one rule item.

    Mirrors packs/rules/debug/'s on-flash layout: a version.txt whose first
    line is the MAJOR.MINOR version, plus an empty __init__.py at every
    package level and the rule module itself. Returns the pack directory.
    """
    aura_packs = mount_root / "aura_packs"
    rules = aura_packs / "rules"
    pack_dir = rules / pack_name
    pack_dir.mkdir(parents=True, exist_ok=True)
    (aura_packs / "__init__.py").touch()
    (rules / "__init__.py").touch()
    (pack_dir / "__init__.py").touch()
    (pack_dir / "version.txt").write_text(version + "\n")
    (pack_dir / f"{item_name}.py").write_text(content)
    return pack_dir


def test_flash_scene_can_reference_and_run_a_card_rule_packs_rule(card_storage):
    """A card rule pack under aura_packs/rules is discovered into the same
    PackRegistry flash rule packs populate -- a flash-registered scene (no
    card scene involved) that declares it in rule_packs resolves and runs
    its rule, proving the pack lands in the shared registry, imported off
    the card, and participates in the running scene."""
    _make_card_rule_pack(
        Path(card_storage.mount_root), "card_pack", "card_rule", _CARD_RULE_PACK_SOURCE
    )
    scene_registry = SceneRegistry()
    scene_registry.register(
        "card_pack_scene",
        lambda: Scene(effect_packs=[], rule_packs=[["card_pack", "1.0"]]),
    )
    hw = _fake_hw(storage=card_storage)

    runtime = build_scene_runtime(hw, "card_pack_scene", scene_registry=scene_registry)
    runtime.manager.active_state.queue_event(Event(_CARD_TEST_EVENT_GROUP, "ping"))
    runtime.manager.update()

    assert runtime.manager.active_state.get_or_none("card_pack_rule_ran", bool) is True


def test_card_scene_can_reference_and_run_a_card_rule_packs_rule(card_storage):
    """A card scene (aura_packs/scenes) that declares a card rule pack
    (aura_packs/rules) in its own rule_packs resolves and runs it end to
    end -- both card slices merge into the same shared registries."""
    _make_card_scene(Path(card_storage.mount_root), "card_scene", rule_packs=[["card_pack", "1.0"]])
    _make_card_rule_pack(
        Path(card_storage.mount_root), "card_pack", "card_rule", _CARD_RULE_PACK_SOURCE
    )
    hw = _fake_hw(storage=card_storage)

    runtime = build_scene_runtime(hw, "card_scene")
    runtime.manager.active_state.queue_event(Event(_CARD_TEST_EVENT_GROUP, "ping"))
    runtime.manager.update()

    assert runtime.manager.active_state.get_or_none("card_pack_rule_ran", bool) is True


def test_card_rule_pack_name_colliding_with_a_flash_rule_pack_raises_at_scan_time(card_storage):
    """A card rule pack sharing a name with a flash rule pack (packs/rules/debug)
    is the existing PackRegistry.scan_dir cross-root collision -- it must halt
    boot loudly rather than silently picking one source over the other."""
    _make_card_rule_pack(
        Path(card_storage.mount_root), "debug", "card_rule", _CARD_RULE_PACK_SOURCE
    )
    hw = _fake_hw(storage=card_storage)

    with pytest.raises(ValueError, match="debug"):
        build_scene_runtime(hw, "tag")


def test_card_with_no_rules_subdirectory_is_a_clean_no_op_for_rule_packs(card_storage):
    """aura_packs/ exists (so sys.path is still appended) but has no rules/
    subdirectory to scan -- this must not raise, only skip the scan, and a
    flash scene still activates normally."""
    aura_packs = Path(card_storage.mount_root) / "aura_packs"
    aura_packs.mkdir(parents=True)
    (aura_packs / "__init__.py").touch()
    hw = _fake_hw(storage=card_storage)

    runtime = build_scene_runtime(hw, "tag")

    assert card_storage.mount_root in sys.path
    assert runtime.manager.active_state is not None

"""Behaviour-driven tests for app/scene_composition.py."""

import json
import sys
from pathlib import Path

import pytest

from app.scene_composition import build_scene_runtime, resolve_boot_scene_name, resolve_ir_codec
from engine.audio import AudioRegistry
from engine.events import Event, EventGroup
from engine.input import ButtonData, InputEvents
from engine.network import LINE
from engine.scene import Scene, SceneRegistry
from engine.state import Scope
from engine.tests.helpers import RecordingSceneReboot, SpyNetworkControls
from hardware.shared.device_hardware import DeviceHardware
from hardware.shared.device_storage import DeviceStorage
from hardware.shared.ir_codecs.aura import AuraInfraredDecoder, AuraInfraredEncoder
from hardware.shared.ir_codecs.tag import TagInfraredDecoder, TagInfraredEncoder
from hardware.shared.tests.helpers import FakeDeviceStorage


def _fake_hw(ir=None, radio=None, audio_registry=None, storage=None, network_controls=None):
    """Return a DeviceHardware built entirely from CPython-safe fakes."""
    return DeviceHardware(
        outputs=[],
        buttons="fake-buttons",
        accelerometer=None,
        magnetometer=None,
        network_controls=(
            network_controls if network_controls is not None else "fake-network-controls"
        ),
        ir=ir,
        radio=radio,
        storage=storage,
        audio_registry=audio_registry,
    )


def test_known_scene_name_activates_that_scenes_local_effects():
    """The tag scene's scene-local 'ready' effect resolves once tag is active."""
    runtime = build_scene_runtime(_fake_hw(), "tag")

    receipt = runtime.effect_manager.set_effect(Scope.PERSONAL, "scene.ready", {})

    assert receipt is not None


def test_ir_range_receiver_scene_boots_and_activates_via_the_standard_pipeline():
    """ir_range_receiver (issue #918) needs no special-casing -- it discovers
    and activates through the same build_scene_runtime path as every other
    scene, proving scene_demo.py can boot straight into it via
    aura-settings.json's default_scene."""
    runtime = build_scene_runtime(_fake_hw(), "ir_range_receiver")

    assert runtime.manager.active_state is not None


def test_unknown_scene_name_raises_naming_the_known_scenes():
    """An unregistered scene name fails loudly instead of falling back to hardware_test."""
    with pytest.raises(ValueError, match="hardware_test"):
        build_scene_runtime(_fake_hw(), "not-a-real-scene")


def test_ir_range_transmitter_scene_is_auto_discovered_by_the_default_disk_scan():
    """packs/scenes/ir_range_transmitter is picked up with no scene_registry
    override -- the same disk scan scene_demo.py's run_scene() uses to resolve
    "ir_range_transmitter" as a flash-configured default_scene (issue #919)."""
    runtime = build_scene_runtime(_fake_hw(), "ir_range_transmitter")

    assert runtime.manager.active_state is not None


def test_ir_range_transmitter_sends_an_ir_packet_on_line_with_no_button_press():
    """The scene auto-starts transmitting on boot: a bare sensor heartbeat with
    no button pressed is enough to trigger a send on LINE (issue #919)."""
    network_spy = SpyNetworkControls()
    runtime = build_scene_runtime(_fake_hw(network_controls=network_spy), "ir_range_transmitter")

    runtime.manager.active_state.queue_event(InputEvents.Sensors(ButtonData(states={})))
    runtime.manager.update()

    assert len(network_spy.send_ir_calls) == 1
    _, emitter = network_spy.send_ir_calls[0]
    assert emitter == LINE


# ---------------------------------------------------------------------------
# resolve_boot_scene_name (issue #902)
# ---------------------------------------------------------------------------


def _scene_registry_with(*scene_names: str) -> SceneRegistry:
    scene_registry = SceneRegistry()
    for scene_name in scene_names:
        scene_registry.register(scene_name, lambda: Scene(effect_packs=[], rule_packs=[]))
    return scene_registry


def test_persisted_sd_scene_overrides_flash_default_when_both_are_known_scenes():
    """A persisted SD override wins even though the flash default is also valid --
    proving resolve_boot_scene's precedence survives the registry-validation wrap."""
    scene_registry = _scene_registry_with("tag", "red_light_green_light")
    storage = FakeDeviceStorage()
    storage.write_json("aura-state.json", {"scene": "tag"})

    scene_name = resolve_boot_scene_name(
        scene_registry, storage, {"default_scene": "red_light_green_light"}
    )

    assert scene_name == "tag"


def test_card_less_device_boots_the_flash_default_scene():
    """hw.storage is None on a card-less device -- the persisted leg is skipped
    entirely and the flash default is used, unaffected."""
    scene_registry = _scene_registry_with("red_light_green_light")

    scene_name = resolve_boot_scene_name(
        scene_registry, None, {"default_scene": "red_light_green_light"}
    )

    assert scene_name == "red_light_green_light"


def test_neither_persisted_nor_flash_scene_raises_naming_both_files():
    """With no SD override and no flash default, boot fails loudly rather than
    silently picking a scene -- the same contract resolve_boot_scene documents."""
    scene_registry = _scene_registry_with("red_light_green_light")
    storage = FakeDeviceStorage()

    with pytest.raises(ValueError, match=r"aura-state\.json.*aura-settings\.json"):
        resolve_boot_scene_name(scene_registry, storage, {})


def test_persisted_scene_unknown_to_the_registry_raises_naming_the_known_scenes():
    """A persisted SD scene name with no matching registry entry fails loudly by
    name here -- the registry-validation step resolve_boot_scene itself skips."""
    scene_registry = _scene_registry_with("red_light_green_light")
    storage = FakeDeviceStorage()
    storage.write_json("aura-state.json", {"scene": "not-a-real-scene"})

    with pytest.raises(ValueError, match="red_light_green_light"):
        resolve_boot_scene_name(scene_registry, storage, {"default_scene": "red_light_green_light"})


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
# build_scene_runtime — scene_reboot port wiring (issue #910)
# ---------------------------------------------------------------------------


def test_build_scene_runtime_wires_the_supplied_scene_reboot_into_the_manager():
    """runtime.manager.reboot_into delegates to the exact scene_reboot instance
    supplied -- proving build_scene_runtime threads it through to SceneManager
    rather than substituting its own."""
    scene_registry = _scene_registry_with("tag")
    scene_reboot = RecordingSceneReboot()

    runtime = build_scene_runtime(
        _fake_hw(), "tag", scene_registry=scene_registry, scene_reboot=scene_reboot
    )
    runtime.manager.reboot_into("tag")

    assert scene_reboot.reboot_into_calls == ["tag"]


def test_build_scene_runtime_with_no_scene_reboot_supplied_still_activates_a_scene():
    """Omitting scene_reboot falls back to a base (unreachable) SceneReboot --
    SceneManager's non-optional seam is satisfied and scene activation is
    otherwise unaffected, even though no rule in this test ever reboots."""
    runtime = build_scene_runtime(_fake_hw(), "tag")

    assert runtime.manager.active_state is not None


# ---------------------------------------------------------------------------
# SceneRuntime.ir wiring (issue #886) -- build_scene_runtime no longer
# assembles a separate IR object; SceneRuntime.ir is hw.ir directly, since
# InfraredTransceiver (hardware/shared/ir_transceiver.py) is now the single
# IR-subsystem owner.
# ---------------------------------------------------------------------------


class _RecordingIrTransceiver:
    """Stands in for an InfraredTransceiver instance -- isolates SceneRuntime
    wiring (identity passthrough) from InfraredTransceiver's own behaviour
    (covered separately in hardware/shared/tests/test_ir_transceiver.py)."""


def test_build_scene_runtime_exposes_the_hardware_bundles_ir_as_runtime_ir():
    """SceneRuntime.ir must be the exact hw.ir instance, not a wrapper or copy."""
    ir = _RecordingIrTransceiver()
    runtime = build_scene_runtime(_fake_hw(ir=ir), "tag")

    assert runtime.ir is ir


def test_build_scene_runtime_ir_is_none_when_the_hardware_bundle_has_no_ir():
    """A device with no ir section wired (hw.ir is None) carries that through
    to the runtime unchanged, rather than substituting a placeholder."""
    runtime = build_scene_runtime(_fake_hw(ir=None), "tag")

    assert runtime.ir is None


# ---------------------------------------------------------------------------
# SceneRuntime.radio wiring (issue #893) -- build_scene_runtime no longer
# assembles a separate per-tick radio orchestrator; SceneRuntime.radio is
# hw.radio directly, since RadioTransceiver
# (hardware/shared/radio_transceiver.py) is now the single radio-subsystem
# owner.
# ---------------------------------------------------------------------------


class _RecordingRadioTransceiver:
    """Stands in for a RadioTransceiver instance -- isolates SceneRuntime
    wiring (identity passthrough) from RadioTransceiver's own behaviour
    (covered separately in hardware/shared/tests/test_radio_transceiver.py)."""


def test_build_scene_runtime_exposes_the_hardware_bundles_radio_as_runtime_radio():
    """SceneRuntime.radio must be the exact hw.radio instance, not a wrapper or copy."""
    radio = _RecordingRadioTransceiver()
    runtime = build_scene_runtime(_fake_hw(radio=radio), "tag")

    assert runtime.radio is radio


def test_build_scene_runtime_radio_is_none_when_the_hardware_bundle_has_no_radio():
    """A device with no radio peripheral wired (hw.radio is None) carries that
    through to the runtime unchanged, rather than substituting a placeholder."""
    runtime = build_scene_runtime(_fake_hw(radio=None), "tag")

    assert runtime.radio is None


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


# ---------------------------------------------------------------------------
# Card effect packs: aura_packs/effects discovery (issue #871)
# ---------------------------------------------------------------------------

_CARD_EFFECT_PACK_BUILD_SOURCE = """\
from effects.effect import AudioPlaybackConfig, Effect, EffectAudio, EffectConfig
from engine.effects.manager import EffectBuilder

_AUDIO = EffectAudio(
    clips={{"start": AudioPlaybackConfig(name="{pack_name}.card_pack_clip", loop=False)}}
)


class _Builder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        return Effect(name=name, pixels=None, audio=_AUDIO)


BUILD = _Builder()
"""


def _make_card_effect_pack(mount_root: Path, pack_name: str, version: str = "1.0") -> Path:
    """Create aura_packs/effects/<pack_name>/ under *mount_root* with one item.

    Mirrors ``_make_card_scene``'s package layout but for an effect pack: a
    ``version.txt`` (the versioning contract ``PackRegistry.scan_dir`` requires)
    plus a single ``glow`` item whose ``BUILD`` returns an effect declaring an
    audio clip qualified by *pack_name*, so a resolved effect proves both the
    module imported off the card and its bundled ``sounds/`` clip is reachable
    under the same ``<pack>.<stem>`` name. Returns the pack directory.
    """
    aura_packs = mount_root / "aura_packs"
    effects = aura_packs / "effects"
    pack_dir = effects / pack_name
    pack_dir.mkdir(parents=True, exist_ok=True)
    (aura_packs / "__init__.py").touch()
    (effects / "__init__.py").touch()
    (pack_dir / "__init__.py").touch()
    (pack_dir / "version.txt").write_text(version)
    (pack_dir / "glow.py").write_text(_CARD_EFFECT_PACK_BUILD_SOURCE.format(pack_name=pack_name))
    return pack_dir


def _add_card_effect_pack_sound(pack_dir: Path, stem: str) -> None:
    sounds_dir = pack_dir / "sounds"
    sounds_dir.mkdir(parents=True, exist_ok=True)
    (sounds_dir / f"{stem}.wav").write_bytes(b"RIFF")  # contents unused; only the path matters


def _register_scene_declaring_effect_pack(
    scene_registry: SceneRegistry, scene_name: str, pack_name: str, version: str = "1.0"
) -> None:
    scene_registry.register(
        scene_name,
        lambda: Scene(effect_packs=[(pack_name, version)], rule_packs=[]),
    )


def test_card_effect_pack_resolves_and_builds_after_importing_off_the_card(card_storage):
    """A card effect pack under aura_packs/effects is discovered into the same
    effect PackRegistry flash packs populate, and its BUILD -- only present on
    the card, nowhere under packs/effects -- imports and builds successfully,
    proving both discovery and on-card import."""
    _make_card_effect_pack(Path(card_storage.mount_root), "card_pack")
    scene_registry = SceneRegistry()
    _register_scene_declaring_effect_pack(scene_registry, "card_pack_scene", "card_pack")
    hw = _fake_hw(storage=card_storage)

    runtime = build_scene_runtime(hw, "card_pack_scene", scene_registry=scene_registry)
    receipt = runtime.effect_manager.set_effect(Scope.PERSONAL, "card_pack.glow", {})

    assert receipt is not None


def test_card_effect_packs_bundled_sound_resolves_to_its_on_card_path(card_storage):
    """A card effect pack's sounds/ clip is recorded at its absolute on-card
    filesystem path and resolves through the same AudioRegistry a flash
    effect-pack clip resolves through, keyed <pack>.<stem>."""
    pack_dir = _make_card_effect_pack(Path(card_storage.mount_root), "card_pack")
    _add_card_effect_pack_sound(pack_dir, "card_pack_clip")
    scene_registry = SceneRegistry()
    _register_scene_declaring_effect_pack(scene_registry, "card_pack_scene", "card_pack")
    hw = _fake_hw(storage=card_storage, audio_registry=AudioRegistry())

    build_scene_runtime(hw, "card_pack_scene", scene_registry=scene_registry)

    expected_path = str(pack_dir / "sounds" / "card_pack_clip.wav")
    assert hw.audio_registry.path("card_pack.card_pack_clip") == expected_path


def test_card_scene_resolves_a_card_effect_pack_end_to_end(card_storage):
    """A card scene (aura_packs/scenes) that declares a card effect pack
    (aura_packs/effects) resolves it through the same shared PackRegistry --
    the two card-only trees merge into the same runtime a flash-only setup
    would use."""
    mount_root = Path(card_storage.mount_root)
    _make_card_effect_pack(mount_root, "card_pack")
    _make_card_scene(
        mount_root,
        "card_scene",
        effect_packs=[["card_pack", "1.0"]],
    )
    hw = _fake_hw(storage=card_storage)

    runtime = build_scene_runtime(hw, "card_scene")
    receipt = runtime.effect_manager.set_effect(Scope.PERSONAL, "card_pack.glow", {})

    assert receipt is not None


def test_card_effect_pack_name_colliding_with_a_flash_pack_raises_at_scan_time(card_storage):
    """A card effect pack sharing a name with a flash effect pack is the
    existing cross-root collision PackRegistry.scan_dir already enforces for
    scenes -- it must halt boot loudly rather than silently picking a source."""
    _make_card_effect_pack(Path(card_storage.mount_root), "basic")
    hw = _fake_hw(storage=card_storage)

    with pytest.raises(ValueError, match="basic"):
        build_scene_runtime(hw, "tag")


def test_card_with_aura_packs_but_no_effects_subdirectory_is_a_clean_no_op(card_storage):
    """aura_packs/ exists (so sys.path is still appended) but has no effects/
    subdirectory to scan -- this must not raise, only skip the scan, and flash
    scene activation continues normally."""
    aura_packs = Path(card_storage.mount_root) / "aura_packs"
    aura_packs.mkdir(parents=True)
    (aura_packs / "__init__.py").touch()
    hw = _fake_hw(storage=card_storage)

    runtime = build_scene_runtime(hw, "tag")

    assert card_storage.mount_root in sys.path
    assert runtime.manager.active_state is not None

"""Behaviour-driven tests for app/scene_composition.py."""

import json
from pathlib import Path

import pytest

from app.scene_composition import (
    build_scene_boot,
    build_scene_runtime,
    resolve_boot_scene_name,
    resolve_ir_codec,
    scan_boot_pack_catalog,
)
from engine.audio import AudioRegistry
from engine.events import Event, EventGroup
from engine.input import ButtonData, InputEvents
from engine.network import LINE
from engine.pack_catalog import PackCatalog, PackScanError, scan_pack_roots
from engine.scene import Scene, SceneRegistry
from engine.state import Scope
from engine.tests.helpers import RecordingSceneReboot, SpyNetworkControls
from hardware.shared.device_hardware import DeviceHardware
from hardware.shared.device_storage import DeviceStorage
from hardware.shared.ir_codecs.aura import AuraInfraredDecoder, AuraInfraredEncoder
from hardware.shared.ir_codecs.tag import TagInfraredDecoder, TagInfraredEncoder


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


def _boot_catalog(storage: DeviceStorage | None = None) -> PackCatalog:
    """Return the boot catalog, scanned the way ``build_scene_boot`` scans it."""
    return scan_boot_pack_catalog(storage)


def test_known_scene_name_activates_that_scenes_local_effects():
    """The tag scene's scene-local 'ready' effect resolves once tag is active."""
    runtime = build_scene_runtime(_fake_hw(), "tag", catalog=_boot_catalog())

    receipt = runtime.effect_manager.set_effect(Scope.PERSONAL, "scene.ready", {})

    assert receipt is not None


def test_ir_range_receiver_scene_boots_and_activates_via_the_standard_pipeline():
    """ir_range_receiver (issue #918) needs no special-casing -- it discovers
    and activates through the same build_scene_runtime path as every other
    scene, proving scene_demo.py can boot straight into it via
    aura-settings.json's default_scene."""
    runtime = build_scene_runtime(_fake_hw(), "ir_range_receiver", catalog=_boot_catalog())

    assert runtime.manager.active_state is not None


def test_unknown_scene_name_raises_naming_the_known_scenes():
    """An unregistered scene name fails loudly instead of falling back to hardware_test."""
    with pytest.raises(ValueError, match="hardware_test"):
        build_scene_runtime(_fake_hw(), "not-a-real-scene", catalog=_boot_catalog())


def test_ir_range_transmitter_scene_is_auto_discovered_by_the_default_disk_scan():
    """packs/scenes/ir_range_transmitter is picked up by scan_boot_pack_catalog's
    flash scan -- the same disk scan scene_demo.py's run_scene() uses to
    resolve "ir_range_transmitter" as a flash-configured default_scene (issue #919)."""
    runtime = build_scene_runtime(_fake_hw(), "ir_range_transmitter", catalog=_boot_catalog())

    assert runtime.manager.active_state is not None


def test_ir_range_transmitter_sends_an_ir_packet_on_line_with_no_button_press():
    """The scene auto-starts transmitting on boot: a bare sensor heartbeat with
    no button pressed is enough to trigger a send on LINE (issue #919)."""
    network_spy = SpyNetworkControls()
    runtime = build_scene_runtime(
        _fake_hw(network_controls=network_spy),
        "ir_range_transmitter",
        catalog=_boot_catalog(),
    )

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


def test_persisted_sd_scene_overrides_flash_default_when_both_are_known_scenes(device_storage):
    """A persisted SD override wins even though the flash default is also valid --
    proving resolve_boot_scene's precedence survives the registry-validation wrap."""
    scene_registry = _scene_registry_with("tag", "red_light_green_light")
    device_storage.write_json("aura-state.json", {"scene": "tag"})

    scene_name = resolve_boot_scene_name(
        scene_registry, device_storage, {"default_scene": "red_light_green_light"}
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


def test_neither_persisted_nor_flash_scene_raises_naming_both_files(device_storage):
    """With no SD override and no flash default, boot fails loudly rather than
    silently picking a scene -- the same contract resolve_boot_scene documents."""
    scene_registry = _scene_registry_with("red_light_green_light")

    with pytest.raises(ValueError, match=r"aura-state\.json.*aura-settings\.json"):
        resolve_boot_scene_name(scene_registry, device_storage, {})


def test_persisted_scene_unknown_to_the_registry_raises_naming_the_known_scenes(device_storage):
    """A persisted SD scene name with no matching registry entry fails loudly by
    name here -- the registry-validation step resolve_boot_scene itself skips."""
    scene_registry = _scene_registry_with("red_light_green_light")
    device_storage.write_json("aura-state.json", {"scene": "not-a-real-scene"})

    with pytest.raises(ValueError, match="red_light_green_light"):
        resolve_boot_scene_name(
            scene_registry, device_storage, {"default_scene": "red_light_green_light"}
        )


# ---------------------------------------------------------------------------
# build_scene_boot: the boot run_scene and the Simulated device share (issue #1020)
# ---------------------------------------------------------------------------


def _no_reset() -> None:
    raise AssertionError("the boot reset the device")


def test_boot_runs_the_scene_the_card_names_over_the_flash_default(device_storage):
    device_storage.write_json("aura-state.json", {"scene": "tag"})

    scene_name, _tick = build_scene_boot(
        _fake_hw(storage=device_storage), {"default_scene": "hardware_test"}, reset=_no_reset
    )

    assert scene_name == "tag"


class _CodecRecordingIr:
    def __init__(self) -> None:
        self.codec: tuple[object, object] | None = None

    def apply_codec(self, encoder_class, decoder_class) -> None:
        self.codec = (encoder_class, decoder_class)


def test_boot_speaks_the_wire_frame_codec_the_booted_scene_declares():
    ir = _CodecRecordingIr()

    build_scene_boot(_fake_hw(ir=ir), {"default_scene": "tag"}, reset=_no_reset)

    assert ir.codec == (TagInfraredEncoder, TagInfraredDecoder)


# ---------------------------------------------------------------------------
# scan_boot_pack_catalog: which pack roots boot scans (issue #1099)
#
# Only the choice of roots is tested here, over the shared device_storage card;
# what a scan finds under them, and how it fails, is the catalog's own suite.
# ---------------------------------------------------------------------------


def _flash_scene_names() -> list[str]:
    return sorted(scan_pack_roots(["packs"]).scene_registry.names())


def test_a_card_less_device_scans_the_flash_root_alone():
    catalog = scan_boot_pack_catalog(None)

    assert sorted(catalog.scene_registry.names()) == _flash_scene_names()


def test_a_card_without_aura_packs_scans_the_flash_root_alone(device_storage):
    catalog = scan_boot_pack_catalog(device_storage)

    assert sorted(catalog.scene_registry.names()) == _flash_scene_names()


def test_a_card_with_aura_packs_scans_the_flash_root_and_the_card_root(device_storage):
    _make_card_scene(Path(device_storage.mount_root), "card_scene")

    catalog = scan_boot_pack_catalog(device_storage)

    assert sorted(catalog.scene_registry.names()) == sorted([*_flash_scene_names(), "card_scene"])


def test_a_misconfigured_card_scene_stops_boot_with_a_pack_scan_error(device_storage):
    _make_card_scene(Path(device_storage.mount_root), "card_scene", version="1")

    with pytest.raises(PackScanError):
        scan_boot_pack_catalog(device_storage)


def test_scene_data_reaches_the_named_scenes_initial_data():
    catalog = scan_boot_pack_catalog(None, scene_data={"tag": {"max_ammo": 2}})

    initial_data = catalog.scene_registry.get("tag").initial_data
    assert initial_data is not None
    assert initial_data["max_ammo"] == 2


def test_a_card_scene_named_as_the_persisted_sd_scene_resolves(device_storage):
    """A card scene named as the persisted SD 'scene' resolves at boot -- the
    catalog scan_boot_pack_catalog builds already carries card scenes, so
    resolve_boot_scene_name's registry-validation step finds it instead of
    raising "unknown scene" (the bug issue #923 fixes)."""
    _make_card_scene(Path(device_storage.mount_root), "card_scene")
    device_storage.write_json("aura-state.json", {"scene": "card_scene"})

    scene_registry = scan_boot_pack_catalog(device_storage).scene_registry
    scene_name = resolve_boot_scene_name(scene_registry, device_storage, {})

    assert scene_name == "card_scene"


def test_a_card_scene_named_as_the_flash_default_scene_resolves(device_storage):
    """A card scene named as the flash 'default_scene' resolves at boot, with
    no persisted SD override in play."""
    _make_card_scene(Path(device_storage.mount_root), "card_scene")

    scene_registry = scan_boot_pack_catalog(device_storage).scene_registry
    scene_name = resolve_boot_scene_name(
        scene_registry, device_storage, {"default_scene": "card_scene"}
    )

    assert scene_name == "card_scene"


def test_a_persisted_card_scene_wins_over_a_flash_default_scene(device_storage):
    """Navigating into a card scene and rebooting persists its name as the SD
    'scene' -- it must win over a *different*, also-valid flash default
    rather than raising "unknown scene": the reboot-survival case issue #923
    fixes."""
    _make_card_scene(Path(device_storage.mount_root), "card_scene")
    device_storage.write_json("aura-state.json", {"scene": "card_scene"})

    scene_registry = scan_boot_pack_catalog(device_storage).scene_registry
    scene_name = resolve_boot_scene_name(scene_registry, device_storage, {"default_scene": "tag"})

    assert scene_name == "card_scene"


def test_unknown_boot_scene_name_raises_naming_both_flash_and_card_scenes(device_storage):
    """A name unknown to either source fails loudly naming every scene the
    complete registry carries -- both flash and card scenes are listed."""
    _make_card_scene(Path(device_storage.mount_root), "card_scene")
    scene_registry = scan_boot_pack_catalog(device_storage).scene_registry

    with pytest.raises(ValueError) as exc_info:
        resolve_boot_scene_name(
            scene_registry, device_storage, {"default_scene": "not-a-real-scene"}
        )

    assert "card_scene" in str(exc_info.value)
    assert "hardware_test" in str(exc_info.value)


# ---------------------------------------------------------------------------
# resolve_ir_codec (issue #862)
# ---------------------------------------------------------------------------


def test_resolve_ir_codec_returns_the_aura_pair_for_a_scene_with_no_declared_codec():
    """A scene with no ir_codec key defaults to the Aura wire-frame codec."""
    scene_registry = SceneRegistry()
    scene_registry.register("no_codec", lambda: Scene(effect_packs=[], rule_packs=[]))

    assert resolve_ir_codec(scene_registry, "no_codec") == (
        AuraInfraredEncoder,
        AuraInfraredDecoder,
    )


def test_resolve_ir_codec_returns_the_tag_pair_for_a_scene_declaring_the_tag_codec():
    """A scene declaring ir_codec: 'tag' resolves to the Tag protocol codec."""
    scene_registry = SceneRegistry()
    scene_registry.register(
        "tag_codec", lambda: Scene(effect_packs=[], rule_packs=[], ir_codec="tag")
    )

    assert resolve_ir_codec(scene_registry, "tag_codec") == (
        TagInfraredEncoder,
        TagInfraredDecoder,
    )


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
    scene_registry = _boot_catalog().scene_registry

    assert resolve_ir_codec(scene_registry, "tag") == (TagInfraredEncoder, TagInfraredDecoder)


# ---------------------------------------------------------------------------
# build_scene_runtime — runs on the supplied catalog (issues #862, #1099)
# ---------------------------------------------------------------------------


def test_build_scene_runtime_activates_a_scene_only_registered_in_the_supplied_catalog():
    """The supplied catalog is used as-is instead of a fresh internal scan --
    this scene exists nowhere under packs/scenes, only in the catalog passed in."""
    catalog = _boot_catalog()
    catalog.scene_registry.register(
        "only_in_supplied_catalog", lambda: Scene(effect_packs=[], rule_packs=[])
    )

    runtime = build_scene_runtime(_fake_hw(), "only_in_supplied_catalog", catalog=catalog)

    assert runtime.manager.active_state is not None


# ---------------------------------------------------------------------------
# build_scene_runtime — scene_reboot port wiring (issue #910)
# ---------------------------------------------------------------------------


def test_build_scene_runtime_wires_the_supplied_scene_reboot_into_the_manager():
    """runtime.manager.reboot_into delegates to the exact scene_reboot instance
    supplied -- proving build_scene_runtime threads it through to SceneManager
    rather than substituting its own."""
    scene_reboot = RecordingSceneReboot()

    runtime = build_scene_runtime(
        _fake_hw(), "tag", catalog=_boot_catalog(), scene_reboot=scene_reboot
    )
    runtime.manager.reboot_into("tag")

    assert scene_reboot.reboot_into_calls == ["tag"]


def test_build_scene_runtime_with_no_scene_reboot_supplied_still_activates_a_scene():
    """Omitting scene_reboot falls back to a base (unreachable) SceneReboot --
    SceneManager's non-optional seam is satisfied and scene activation is
    otherwise unaffected, even though no rule in this test ever reboots."""
    runtime = build_scene_runtime(_fake_hw(), "tag", catalog=_boot_catalog())

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
    runtime = build_scene_runtime(_fake_hw(ir=ir), "tag", catalog=_boot_catalog())

    assert runtime.ir is ir


def test_build_scene_runtime_ir_is_none_when_the_hardware_bundle_has_no_ir():
    """A device with no ir section wired (hw.ir is None) carries that through
    to the runtime unchanged, rather than substituting a placeholder."""
    runtime = build_scene_runtime(_fake_hw(ir=None), "tag", catalog=_boot_catalog())

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
    runtime = build_scene_runtime(_fake_hw(radio=radio), "tag", catalog=_boot_catalog())

    assert runtime.radio is radio


def test_build_scene_runtime_radio_is_none_when_the_hardware_bundle_has_no_radio():
    """A device with no radio peripheral wired (hw.radio is None) carries that
    through to the runtime unchanged, rather than substituting a placeholder."""
    runtime = build_scene_runtime(_fake_hw(radio=None), "tag", catalog=_boot_catalog())

    assert runtime.radio is None


# ---------------------------------------------------------------------------
# Audio registry wiring: pack sounds base + scene overlay (issue #804)
# ---------------------------------------------------------------------------


def test_build_scene_runtime_installs_the_catalogs_pack_sounds_in_the_devices_audio_registry():
    """The catalog's packs/effects/*/sounds clips become hw.audio_registry's base, qualified
    by pack name, so basic.game_over_sting_start resolves once the runtime is built."""
    hw = _fake_hw(audio_registry=AudioRegistry())

    build_scene_runtime(hw, "hardware_test", catalog=_boot_catalog())

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

    build_scene_runtime(hw, "hardware_test", catalog=_boot_catalog())

    assert (
        hw.audio_registry.path("scene.sfx_test_start")
        == "packs/scenes/hardware_test/sounds/sfx_test_start.wav"
    )


def test_build_scene_runtime_with_no_audio_registry_still_activates_scene():
    """A device with no enabled audio section (hw.audio_registry is None) gets no
    pack sounds and no overlay wiring, but scene activation is otherwise unaffected."""
    hw = _fake_hw()

    runtime = build_scene_runtime(hw, "hardware_test", catalog=_boot_catalog())

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

    build_scene_runtime(hw, "tag", catalog=_boot_catalog())

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
    own -- it must resolve from the pack sounds base, not from tag's sounds/ overlay."""
    hw = _fake_hw(audio_registry=AudioRegistry())

    build_scene_runtime(hw, "tag", catalog=_boot_catalog())

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

    build_scene_runtime(hw, "red_light_green_light", catalog=_boot_catalog())

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
    own -- it must resolve from the pack sounds base, not from rlgl's sounds/ overlay."""
    hw = _fake_hw(audio_registry=AudioRegistry())

    build_scene_runtime(hw, "red_light_green_light", catalog=_boot_catalog())

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


def test_build_scene_runtime_discovers_and_activates_a_card_scene(device_storage):
    """A scene that exists only under the card's aura_packs/scenes is selectable
    at boot -- it loads into the same SceneRegistry flash scenes populate."""
    _make_card_scene(Path(device_storage.mount_root), "card_scene")
    hw = _fake_hw(storage=device_storage)

    runtime = build_scene_runtime(hw, "card_scene", catalog=_boot_catalog(device_storage))

    assert runtime.manager.active_state is not None


def test_card_scenes_local_rule_imports_off_the_card_and_handles_events(device_storage):
    """A card scene's scene-local rule is imported through the aura_packs. prefix
    against the card and receives events like any other scene-local rule."""
    scene_dir = _make_card_scene(Path(device_storage.mount_root), "card_scene")
    _add_card_scene_rule(scene_dir, "card_rule", _CARD_RULE_SOURCE)
    hw = _fake_hw(storage=device_storage)

    runtime = build_scene_runtime(hw, "card_scene", catalog=_boot_catalog(device_storage))
    runtime.manager.active_state.queue_event(Event(_CARD_TEST_EVENT_GROUP, "ping"))
    runtime.manager.update()

    assert runtime.manager.active_state.get_or_none("card_rule_ran", bool) is True


def test_card_scenes_local_effect_imports_off_the_card_and_resolves_at_runtime(device_storage):
    """A card scene's scene-local effect is imported through the aura_packs. prefix
    and resolves via the same scene. prefix a flash scene-local effect uses."""
    scene_dir = _make_card_scene(Path(device_storage.mount_root), "card_scene")
    _add_card_scene_effect(scene_dir, "card_effect", _CARD_EFFECT_SOURCE)
    _add_card_scene_sound(scene_dir, "card_clip")
    hw = _fake_hw(storage=device_storage)

    runtime = build_scene_runtime(hw, "card_scene", catalog=_boot_catalog(device_storage))
    receipt = runtime.effect_manager.set_effect(Scope.PERSONAL, "scene.card_effect", {})

    assert receipt is not None


def test_card_scenes_bundled_sound_resolves_to_its_on_card_path(device_storage):
    """A card scene's sounds/ clip is recorded at its absolute on-card filesystem
    path -- resolved through the DeviceStorage port, never a re-derived '/sd' --
    and reaches the same AudioRegistry a flash scene's clip resolves through."""
    scene_dir = _make_card_scene(Path(device_storage.mount_root), "card_scene")
    _add_card_scene_sound(scene_dir, "card_clip")
    hw = _fake_hw(storage=device_storage, audio_registry=AudioRegistry())

    build_scene_runtime(hw, "card_scene", catalog=_boot_catalog(device_storage))

    expected_path = str(scene_dir / "sounds" / "card_clip.wav")
    assert hw.audio_registry.path("scene.card_clip") == expected_path


def test_card_with_no_aura_packs_directory_still_activates_a_flash_scene(device_storage):
    """Storage is present but the card carries no top-level aura_packs/ -- flash
    scene selection still works normally despite the (no-op) card scan."""
    hw = _fake_hw(storage=device_storage)

    runtime = build_scene_runtime(hw, "tag", catalog=_boot_catalog(device_storage))

    assert runtime.manager.active_state is not None


def test_card_with_an_empty_aura_packs_directory_still_activates_a_flash_scene(device_storage):
    """aura_packs/ exists but has no scenes/, rules/ or effects/ subdirectory --
    the card root is still scanned, contributes nothing, and boot goes on."""
    aura_packs = Path(device_storage.mount_root) / "aura_packs"
    aura_packs.mkdir(parents=True)
    (aura_packs / "__init__.py").touch()
    hw = _fake_hw(storage=device_storage)

    runtime = build_scene_runtime(hw, "tag", catalog=_boot_catalog(device_storage))

    assert runtime.manager.active_state is not None


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


def test_flash_scene_can_reference_and_run_a_card_rule_packs_rule(device_storage):
    """A card rule pack under aura_packs/rules is discovered into the same
    PackRegistry flash rule packs populate -- a flash-registered scene (no
    card scene involved) that declares it in rule_packs resolves and runs
    its rule, proving the pack lands in the shared registry, imported off
    the card, and participates in the running scene."""
    _make_card_rule_pack(
        Path(device_storage.mount_root), "card_pack", "card_rule", _CARD_RULE_PACK_SOURCE
    )
    catalog = _boot_catalog(device_storage)
    catalog.scene_registry.register(
        "card_pack_scene",
        lambda: Scene(effect_packs=[], rule_packs=[["card_pack", "1.0"]]),
    )
    hw = _fake_hw(storage=device_storage)

    runtime = build_scene_runtime(hw, "card_pack_scene", catalog=catalog)
    runtime.manager.active_state.queue_event(Event(_CARD_TEST_EVENT_GROUP, "ping"))
    runtime.manager.update()

    assert runtime.manager.active_state.get_or_none("card_pack_rule_ran", bool) is True


def test_card_scene_can_reference_and_run_a_card_rule_packs_rule(device_storage):
    """A card scene (aura_packs/scenes) that declares a card rule pack
    (aura_packs/rules) in its own rule_packs resolves and runs it end to
    end -- both card slices merge into the same shared registries."""
    _make_card_scene(
        Path(device_storage.mount_root), "card_scene", rule_packs=[["card_pack", "1.0"]]
    )
    _make_card_rule_pack(
        Path(device_storage.mount_root), "card_pack", "card_rule", _CARD_RULE_PACK_SOURCE
    )
    hw = _fake_hw(storage=device_storage)

    runtime = build_scene_runtime(hw, "card_scene", catalog=_boot_catalog(device_storage))
    runtime.manager.active_state.queue_event(Event(_CARD_TEST_EVENT_GROUP, "ping"))
    runtime.manager.update()

    assert runtime.manager.active_state.get_or_none("card_pack_rule_ran", bool) is True


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
    ``version.txt`` (the marker the pack catalog requires)
    plus a single ``glow`` item whose ``BUILD`` returns an effect declaring an
    audio clip qualified by *pack_name*, and the ``sounds/card_pack_clip.wav``
    that clip names (building the effect resolves it), so a resolved effect proves both the
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
    _add_card_effect_pack_sound(pack_dir, "card_pack_clip")
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


def test_card_effect_pack_resolves_and_builds_after_importing_off_the_card(device_storage):
    """A card effect pack under aura_packs/effects is discovered into the same
    effect PackRegistry flash packs populate, and its BUILD -- only present on
    the card, nowhere under packs/effects -- imports and builds successfully,
    proving both discovery and on-card import."""
    _make_card_effect_pack(Path(device_storage.mount_root), "card_pack")
    catalog = _boot_catalog(device_storage)
    _register_scene_declaring_effect_pack(catalog.scene_registry, "card_pack_scene", "card_pack")
    hw = _fake_hw(storage=device_storage)

    runtime = build_scene_runtime(hw, "card_pack_scene", catalog=catalog)
    receipt = runtime.effect_manager.set_effect(Scope.PERSONAL, "card_pack.glow", {})

    assert receipt is not None


def test_card_effect_packs_bundled_sound_resolves_to_its_on_card_path(device_storage):
    """A card effect pack's sounds/ clip is recorded at its absolute on-card
    filesystem path and resolves through the same AudioRegistry a flash
    effect-pack clip resolves through, keyed <pack>.<stem>."""
    pack_dir = _make_card_effect_pack(Path(device_storage.mount_root), "card_pack")
    catalog = _boot_catalog(device_storage)
    _register_scene_declaring_effect_pack(catalog.scene_registry, "card_pack_scene", "card_pack")
    hw = _fake_hw(storage=device_storage, audio_registry=AudioRegistry())

    build_scene_runtime(hw, "card_pack_scene", catalog=catalog)

    expected_path = str(pack_dir / "sounds" / "card_pack_clip.wav")
    assert hw.audio_registry.path("card_pack.card_pack_clip") == expected_path


def test_card_scene_resolves_a_card_effect_pack_end_to_end(device_storage):
    """A card scene (aura_packs/scenes) that declares a card effect pack
    (aura_packs/effects) resolves it through the same shared PackRegistry --
    the two card-only trees merge into the same runtime a flash-only setup
    would use."""
    mount_root = Path(device_storage.mount_root)
    _make_card_effect_pack(mount_root, "card_pack")
    _make_card_scene(
        mount_root,
        "card_scene",
        effect_packs=[["card_pack", "1.0"]],
    )
    hw = _fake_hw(storage=device_storage)

    runtime = build_scene_runtime(hw, "card_scene", catalog=_boot_catalog(device_storage))
    receipt = runtime.effect_manager.set_effect(Scope.PERSONAL, "card_pack.glow", {})

    assert receipt is not None

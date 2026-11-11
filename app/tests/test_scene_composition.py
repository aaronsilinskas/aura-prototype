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
from engine.input import ButtonData, InputEvents
from engine.log import Logger
from engine.network import LINE
from engine.pack_catalog import PackCatalog, PackScanError, scan_pack_roots
from engine.scene import Scene, SceneRegistry
from engine.state import Scope
from engine.tests.helpers import RecordingSceneReboot, SpyNetworkControls, active_state
from hardware.shared.debounced_buttons import DebouncedButtons
from hardware.shared.device_hardware import DeviceHardware
from hardware.shared.device_storage import DeviceStorage
from hardware.shared.ir_codecs.aura import AuraInfraredDecoder, AuraInfraredEncoder
from hardware.shared.ir_codecs.tag import TagInfraredDecoder, TagInfraredEncoder

_FULL = frozenset(
    (
        "button.A",
        "button.B",
        "accelerometer",
        "magnetometer",
        "radio",
        "storage",
        "ir.line",
        "ir.cone",
        "ir.area_of_effect",
        "ir.receive",
    )
)
"""Every Capability a fully built simulated device has."""


def _fake_hw(ir=None, radio=None, storage=None, network_controls=None, capabilities=_FULL):
    """Return a DeviceHardware built entirely from CPython-safe fakes."""
    return DeviceHardware(
        outputs=[],
        buttons=DebouncedButtons([]),
        accelerometer=None,
        magnetometer=None,
        network_controls=(
            network_controls if network_controls is not None else SpyNetworkControls()
        ),
        ir=ir,
        radio=radio,
        storage=storage,
        capabilities=capabilities,
        polled=(),
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
    aura-boot.json's default_scene."""
    runtime = build_scene_runtime(_fake_hw(), "ir_range_receiver", catalog=_boot_catalog())

    assert runtime.manager.active_state is not None


def test_the_active_scenes_rules_see_the_devices_capabilities():
    hw = _fake_hw(capabilities=frozenset(("radio", "button.A", "button.B", "storage")))

    runtime = build_scene_runtime(hw, "hardware_test", catalog=_boot_catalog())

    state = active_state(runtime.manager)
    capabilities = state.capabilities
    assert (capabilities.has("radio"), capabilities.has("ir.line")) == (True, False)


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

    state = active_state(runtime.manager)
    state.queue_event(InputEvents.Sensors(ButtonData(states={})))
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
    proving boot_scene_candidates' precedence survives the registry-validation wrap."""
    scene_registry = _scene_registry_with("tag", "red_light_green_light")
    device_storage.write_json("aura-state.json", {"scene": "tag"})

    scene_name = resolve_boot_scene_name(
        scene_registry, device_storage, {"default_scene": "red_light_green_light"}, _FULL
    )

    assert scene_name == "tag"


def test_card_less_device_boots_the_flash_default_scene():
    """hw.storage is None on a card-less device -- the persisted leg is skipped
    entirely and the flash default is used, unaffected."""
    scene_registry = _scene_registry_with("red_light_green_light")

    scene_name = resolve_boot_scene_name(
        scene_registry, None, {"default_scene": "red_light_green_light"}, _FULL
    )

    assert scene_name == "red_light_green_light"


def test_neither_persisted_nor_flash_scene_raises_naming_both_files(device_storage):
    """With no SD override and no flash default, boot fails loudly rather than
    silently picking a scene -- the same contract boot_scene_candidates documents."""
    scene_registry = _scene_registry_with("red_light_green_light")

    with pytest.raises(ValueError, match=r"aura-state\.json.*aura-boot\.json"):
        resolve_boot_scene_name(scene_registry, device_storage, {}, _FULL)


def test_persisted_scene_unknown_to_the_registry_raises_naming_the_known_scenes(device_storage):
    """A persisted SD scene name with no matching registry entry fails loudly by
    name here -- the registry-validation step boot_scene_candidates itself skips."""
    scene_registry = _scene_registry_with("red_light_green_light")
    device_storage.write_json("aura-state.json", {"scene": "not-a-real-scene"})

    with pytest.raises(ValueError, match="red_light_green_light"):
        resolve_boot_scene_name(
            scene_registry, device_storage, {"default_scene": "red_light_green_light"}, _FULL
        )


def test_skipping_a_persisted_scene_logs_one_line_naming_it_and_what_it_lacks(device_storage):
    scene_registry = scan_boot_pack_catalog(None).scene_registry
    device_storage.write_json("aura-state.json", {"scene": "red_light_green_light"})
    lines: list[str] = []

    resolve_boot_scene_name(
        scene_registry,
        device_storage,
        {"default_scene": "hardware_test"},
        _FULL - {"accelerometer"},
        Logger("[boot]", sink=lines.append),
    )

    assert len(lines) == 1
    assert "red_light_green_light" in lines[0]
    assert "accelerometer" in lines[0]


# ---------------------------------------------------------------------------
# build_scene_boot: the boot run_scene and the Simulated device share (issue #1020)
# ---------------------------------------------------------------------------


def _no_reset() -> None:
    raise AssertionError("the boot reset the device")


def test_boot_runs_the_scene_the_card_names_over_the_flash_default(device_storage):
    device_storage.write_json("aura-state.json", {"scene": "tag"})

    boot = build_scene_boot(
        _fake_hw(storage=device_storage), {"default_scene": "hardware_test"}, reset=_no_reset
    )

    assert boot.scene_name == "tag"


class _CodecRecordingIr:
    def __init__(self) -> None:
        self.codec: tuple[object, object] | None = None

    def apply_codec(self, encoder_class, decoder_factory) -> None:
        self.codec = (encoder_class, decoder_factory)


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


def test_setting_overrides_reach_the_named_scenes_settings():
    catalog = scan_boot_pack_catalog(
        None, setting_overrides={"tag": {"settings": {"starting_hitpoints": 2}}}
    )

    settings = catalog.scene_registry.get("tag").settings
    assert settings.get_int("scene", "starting_hitpoints") == 2


def test_a_card_scene_named_as_the_persisted_sd_scene_resolves(device_storage):
    """A card scene named as the persisted SD 'scene' resolves at boot -- the
    catalog scan_boot_pack_catalog builds already carries card scenes, so
    resolve_boot_scene_name's registry-validation step finds it instead of
    raising "unknown scene" (the bug issue #923 fixes)."""
    _make_card_scene(Path(device_storage.mount_root), "card_scene")
    device_storage.write_json("aura-state.json", {"scene": "card_scene"})

    scene_registry = scan_boot_pack_catalog(device_storage).scene_registry
    scene_name = resolve_boot_scene_name(scene_registry, device_storage, {}, _FULL)

    assert scene_name == "card_scene"


def test_a_card_scene_named_as_the_flash_default_scene_resolves(device_storage):
    """A card scene named as the flash 'default_scene' resolves at boot, with
    no persisted SD override in play."""
    _make_card_scene(Path(device_storage.mount_root), "card_scene")

    scene_registry = scan_boot_pack_catalog(device_storage).scene_registry
    scene_name = resolve_boot_scene_name(
        scene_registry, device_storage, {"default_scene": "card_scene"}, _FULL
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
    scene_name = resolve_boot_scene_name(
        scene_registry, device_storage, {"default_scene": "tag"}, _FULL
    )

    assert scene_name == "card_scene"


def test_unknown_boot_scene_name_raises_naming_both_flash_and_card_scenes(device_storage):
    """A name unknown to either source fails loudly naming every scene the
    complete registry carries -- both flash and card scenes are listed."""
    _make_card_scene(Path(device_storage.mount_root), "card_scene")
    scene_registry = scan_boot_pack_catalog(device_storage).scene_registry

    with pytest.raises(ValueError) as exc_info:
        resolve_boot_scene_name(
            scene_registry, device_storage, {"default_scene": "not-a-real-scene"}, _FULL
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
# Card scenes
# ---------------------------------------------------------------------------


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

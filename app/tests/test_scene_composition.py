"""Behaviour-driven tests for the Scene boot, ``build_scene_boot``: each boots fake
hardware and checks which scene it booted, what that scene's rules saw, or what
the boot logged, persisted or raised."""

import pytest

from app.scene_composition import build_scene_boot
from app.tests.probe import PROBE_SCENE
from engine.capabilities import MissingCapabilityError
from engine.events import Event
from engine.log import Logger
from engine.pack_catalog import PackScanError, scan_pack_roots
from engine.tests.helpers import SpyNetworkControls
from hardware.shared.debounced_buttons import DebouncedButtons
from hardware.shared.device_hardware import DeviceHardware
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

_FLASH_SCENE = "hardware_test"
"""A flash scene with no Required capabilities."""


def _hw(storage=None, ir=None, capabilities=_FULL):
    """Return a DeviceHardware built entirely from CPython-safe fakes."""
    return DeviceHardware(
        outputs=[],
        buttons=DebouncedButtons([]),
        accelerometer=None,
        magnetometer=None,
        network_controls=SpyNetworkControls(),
        ir=ir,
        radio=None,
        storage=storage,
        capabilities=capabilities,
        polled=(),
    )


def _no_reset() -> None:
    raise AssertionError("the boot reset the device")


def _known_scenes(error: pytest.ExceptionInfo[ValueError]) -> list[str]:
    """Return the known scenes an unknown-scene error names, sorted."""
    return sorted(str(error.value).split("known scenes: ")[1].split(", "))


def _flash_scenes() -> list[str]:
    return sorted(scan_pack_roots(["packs"]).scene_registry.names())


class _CodecRecordingIr:
    """Stands in for the device's IR, recording the wire-frame codec applied to it."""

    def __init__(self) -> None:
        self.codec: tuple[object, object] | None = None

    def apply_codec(self, encoder_class, decoder_factory) -> None:
        self.codec = (encoder_class, decoder_factory)


# ---------------------------------------------------------------------------
# Which scene boots
# ---------------------------------------------------------------------------


def test_the_cards_persisted_scene_boots_over_the_flash_default_scene(probe):
    probe.storage.write_json("aura-state.json", {"scene": PROBE_SCENE})

    boot = probe.boot(_hw(probe.storage), boot_mapping={"default_scene": _FLASH_SCENE})

    assert boot.scene_name == PROBE_SCENE


def test_a_card_less_device_boots_the_flash_default_scene():
    boot = build_scene_boot(_hw(), {"default_scene": _FLASH_SCENE}, reset=_no_reset)

    assert boot.scene_name == _FLASH_SCENE


def test_boot_raises_naming_both_boot_files_when_neither_names_a_scene(probe):
    with pytest.raises(ValueError, match=r"aura-state\.json.*aura-boot\.json"):
        probe.boot(_hw(probe.storage), boot_mapping={})


def test_boot_raises_naming_the_known_scenes_when_the_persisted_scene_is_unknown(probe):
    probe.storage.write_json("aura-state.json", {"scene": "not-a-real-scene"})

    with pytest.raises(ValueError, match=_FLASH_SCENE):
        probe.boot(_hw(probe.storage), boot_mapping={"default_scene": _FLASH_SCENE})


def test_a_persisted_scene_the_device_cant_run_is_skipped_for_the_flash_default(probe):
    probe.storage.write_json("aura-state.json", {"scene": PROBE_SCENE})

    boot = probe.boot(
        _hw(probe.storage, capabilities=_FULL - {"accelerometer"}),
        scene_json={"requires": ["accelerometer"]},
        boot_mapping={"default_scene": _FLASH_SCENE},
    )

    assert boot.scene_name == _FLASH_SCENE


def test_skipping_a_persisted_scene_logs_one_line_naming_it_and_what_it_lacks(probe):
    probe.storage.write_json("aura-state.json", {"scene": PROBE_SCENE})
    lines: list[str] = []

    probe.boot(
        _hw(probe.storage, capabilities=_FULL - {"accelerometer"}),
        scene_json={"requires": ["accelerometer"]},
        boot_mapping={"default_scene": _FLASH_SCENE},
        logger=Logger("[boot]", sink=lines.append),
    )

    [line] = lines
    assert PROBE_SCENE in line
    assert "accelerometer" in line


def test_boot_raises_missing_capability_when_no_candidate_fits_the_device(probe):
    with pytest.raises(MissingCapabilityError, match="accelerometer"):
        probe.boot(
            _hw(probe.storage, capabilities=_FULL - {"accelerometer"}),
            scene_json={"requires": ["accelerometer"]},
        )


# ---------------------------------------------------------------------------
# Scene deploy token
# ---------------------------------------------------------------------------


def test_a_pending_scene_deploy_token_boots_the_deployed_scene_over_a_stale_persisted_one(probe):
    probe.storage.write_json("aura-state.json", {"scene": _FLASH_SCENE})

    boot = probe.boot(
        _hw(probe.storage),
        boot_mapping={"default_scene": PROBE_SCENE, "scene_deploy_token": "deploy-1"},
    )

    assert boot.scene_name == PROBE_SCENE


def test_an_applied_scene_deploy_token_no_longer_overrides_the_persisted_scene(probe):
    boot_mapping = {"default_scene": PROBE_SCENE, "scene_deploy_token": "deploy-1"}
    probe.storage.write_json("aura-state.json", {"scene": _FLASH_SCENE})
    probe.boot(_hw(probe.storage), boot_mapping=boot_mapping)
    probe.storage.write_json(
        "aura-state.json",
        {**(probe.storage.read_json("aura-state.json") or {}), "scene": _FLASH_SCENE},
    )

    boot = probe.boot(_hw(probe.storage), boot_mapping=boot_mapping)

    assert boot.scene_name == _FLASH_SCENE


# ---------------------------------------------------------------------------
# Which pack roots boot scans
# ---------------------------------------------------------------------------


def test_a_card_less_device_reaches_only_the_flash_scenes():
    with pytest.raises(ValueError) as error:
        build_scene_boot(_hw(), {"default_scene": "not-a-real-scene"}, reset=_no_reset)

    assert _known_scenes(error) == _flash_scenes()


def test_a_card_without_aura_packs_reaches_only_the_flash_scenes(device_storage):
    with pytest.raises(ValueError) as error:
        build_scene_boot(
            _hw(device_storage), {"default_scene": "not-a-real-scene"}, reset=_no_reset
        )

    assert _known_scenes(error) == _flash_scenes()


def test_a_card_with_aura_packs_reaches_the_flash_scenes_and_the_cards(probe):
    with pytest.raises(ValueError) as error:
        probe.boot(_hw(probe.storage), boot_mapping={"default_scene": "not-a-real-scene"})

    assert _known_scenes(error) == sorted([*_flash_scenes(), PROBE_SCENE])


def test_a_misconfigured_card_scene_stops_boot_with_a_pack_scan_error(probe):
    with pytest.raises(PackScanError):
        probe.boot(_hw(probe.storage), scene_json={"version": "1"})


# ---------------------------------------------------------------------------
# Wire-frame codec
# ---------------------------------------------------------------------------


def test_boot_applies_the_booted_scenes_declared_codec_to_the_ir_before_the_first_tick(probe):
    ir = _CodecRecordingIr()

    probe.boot(_hw(probe.storage, ir=ir), scene_json={"ir_codec": "tag"})

    assert ir.codec == (TagInfraredEncoder, TagInfraredDecoder)


def test_a_scene_declaring_no_codec_boots_on_the_aura_wire_frame(probe):
    ir = _CodecRecordingIr()

    probe.boot(_hw(probe.storage, ir=ir))

    assert ir.codec == (AuraInfraredEncoder, AuraInfraredDecoder)


def test_a_scene_declaring_an_unknown_codec_fails_boot_naming_it(probe):
    with pytest.raises(ValueError, match="tv_remote"):
        probe.boot(_hw(probe.storage, ir=_CodecRecordingIr()), scene_json={"ir_codec": "tv_remote"})


# ---------------------------------------------------------------------------
# What the booted scene's rules see
# ---------------------------------------------------------------------------


def test_setting_overrides_reach_the_booted_scenes_settings(probe):
    tick = probe.boot(
        _hw(probe.storage),
        scene_json={
            "settings": {"rounds": {"type": "int", "default": 1, "description": "Rounds."}}
        },
        setting_overrides={PROBE_SCENE: {"settings": {"rounds": 2}}},
    ).tick

    tick()

    [(_, state), *_] = probe.heard(Event)
    assert state.settings.get_int("scene", "rounds") == 2


def test_the_booted_scenes_rules_see_the_devices_capabilities(probe):
    tick = probe.boot(_hw(probe.storage, capabilities=frozenset(("radio", "storage")))).tick

    tick()

    [(_, state), *_] = probe.heard(Event)
    assert (state.capabilities.has("radio"), state.capabilities.has("ir.line")) == (True, False)


# ---------------------------------------------------------------------------
# Reboots
# ---------------------------------------------------------------------------


def test_a_reboot_the_booted_scene_asks_for_persists_its_target_then_resets(probe):
    persisted_at_reset: list[dict | None] = []
    tick = probe.boot(
        _hw(probe.storage),
        reset=lambda: persisted_at_reset.append(probe.storage.read_json("aura-state.json")),
    ).tick
    tick()
    [(_, state), *_] = probe.heard(Event)

    state.scene_controls.reboot_into(_FLASH_SCENE)

    [persisted] = persisted_at_reset
    assert persisted is not None
    assert persisted["scene"] == _FLASH_SCENE

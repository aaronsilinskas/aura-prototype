"""Behaviour-driven tests for the Scene boot, ``build_scene_boot``: each boots fake
hardware and checks which scene it booted, what that scene's rules saw, or what
the boot logged, persisted or raised."""

import pytest

from app.scene_composition import build_scene_boot
from app.tests.probe import PROBE_SCENE, no_reset
from engine.capabilities import MissingCapabilityError
from engine.log import Logger
from engine.pack_catalog import PackScanError
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
    """Return a DeviceHardware built entirely from CPython-safe fakes; *ir* is Polled."""
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
        polled=(ir,) if ir is not None else (),
    )


class _CodecRecordingIr:
    """Stands in for the device's IR, recording the codec applied to it and each use, in order.

    ``uses`` logs ``("apply_codec", (encoder, decoder))``, ``("update", None)`` for
    each poll, and ``("received", None)`` for each read of a received packet.
    """

    def __init__(self) -> None:
        self.codec: tuple[object, object] | None = None
        self.uses: list[tuple[str, object]] = []
        self.last_signal_strength = 0
        self.last_error_margin = 0

    def apply_codec(self, encoder_class, decoder_factory) -> None:
        self.codec = (encoder_class, decoder_factory)
        self.uses.append(("apply_codec", self.codec))

    def update(self, elapsed: float) -> None:
        self.uses.append(("update", None))

    @property
    def received(self) -> bytes | None:
        self.uses.append(("received", None))
        return None

    def telemetry_line(self) -> str | None:
        return None


# ---------------------------------------------------------------------------
# Which scene boots
# ---------------------------------------------------------------------------


def test_the_cards_persisted_scene_boots_over_the_flash_default_scene(probe):
    probe.storage.write_json("aura-state.json", {"scene": PROBE_SCENE})

    boot = probe.boot(_hw(probe.storage), boot_mapping={"default_scene": _FLASH_SCENE})

    assert boot.scene_name == PROBE_SCENE


def test_a_card_less_device_boots_the_flash_default_scene():
    boot = build_scene_boot(_hw(), {"default_scene": _FLASH_SCENE}, reset=no_reset)

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


def test_a_device_without_the_card_cannot_boot_a_scene_only_that_card_carries(probe):
    with pytest.raises(ValueError, match=f"unknown scene {PROBE_SCENE!r}"):
        probe.boot(_hw(storage=None))


def test_a_card_without_aura_packs_still_boots_a_flash_scene(device_storage):
    boot = build_scene_boot(_hw(device_storage), {"default_scene": _FLASH_SCENE}, reset=no_reset)

    assert boot.scene_name == _FLASH_SCENE


def test_a_card_with_aura_packs_boots_its_own_scene(probe):
    boot = probe.boot(_hw(probe.storage))

    assert boot.scene_name == PROBE_SCENE


def test_a_card_with_aura_packs_still_boots_a_flash_scene(probe):
    boot = probe.boot(_hw(probe.storage), boot_mapping={"default_scene": _FLASH_SCENE})

    assert boot.scene_name == _FLASH_SCENE


def test_a_misconfigured_card_scene_stops_boot_with_a_pack_scan_error(probe):
    with pytest.raises(PackScanError):
        probe.boot(_hw(probe.storage), scene_json={"version": "1"})


# ---------------------------------------------------------------------------
# Wire-frame codec
# ---------------------------------------------------------------------------


def test_boot_applies_the_booted_scenes_declared_codec_to_the_ir_before_the_first_tick(probe):
    ir = _CodecRecordingIr()
    tick = probe.boot(_hw(probe.storage, ir=ir), scene_json={"ir_codec": "tag"}).tick

    tick()

    first_use, *later_uses = ir.uses
    assert first_use == ("apply_codec", (TagInfraredEncoder, TagInfraredDecoder))
    assert {use for use, _ in later_uses} == {"update", "received"}


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

    assert probe.state().settings.get_int("scene", "rounds") == 2


def test_the_booted_scenes_rules_see_the_devices_capabilities(probe):
    tick = probe.boot(_hw(probe.storage, capabilities=frozenset(("radio", "storage")))).tick

    tick()

    state = probe.state()
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

    probe.state().scene_controls.reboot_into(_FLASH_SCENE)

    [persisted] = persisted_at_reset
    assert persisted is not None
    assert persisted["scene"] == _FLASH_SCENE


def test_the_boots_scene_controls_are_the_ones_the_booted_scenes_rules_hold(probe):
    boot = probe.boot(_hw(probe.storage))
    boot.tick()

    assert boot.scene_controls is probe.state().scene_controls

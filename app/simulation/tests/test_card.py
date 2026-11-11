"""A Simulated device's card is a real directory: card scenes and card packs work as on a device."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

from app.simulation import Simulation
from engine.capabilities import MissingCapabilityError
from engine.state import Scope

_GREEN = 0x00FF00
_BLUE = 0x0000FF

_LIGHTING_RULE = """\
from engine.engine import GameRule
from engine.input import InputEvents
from engine.state import GameState, Scope


class _Light(GameRule):
    def __init__(self) -> None:
        self.on(InputEvents.Sensors, self._handle)

    def _handle(self, event: InputEvents.Sensors, state: GameState) -> None:
        state.effect_controls.set_effect(Scope.PERSONAL, {effect!r}, {{"color": {color}}})


RULE = _Light()
"""

_SOLID_EFFECT = """\
from effects.effect import Effect, EffectConfig, EffectPixels, PixelBuffer
from engine.effects.builder import EffectBuilder


class _Solid(EffectPixels):
    def __init__(self, color: int) -> None:
        self._color = color

    def update(self, elapsed: float) -> None:
        pass

    def render(self, output: PixelBuffer) -> None:
        for i in range(len(output)):
            output[i] = self._color


class _Builder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        return Effect(name=name, pixels=_Solid(config.get_option("color", 0)))


BUILD = _Builder()
"""

_CHIME_EFFECT = """\
from effects.effect import AudioPlaybackConfig, Effect, EffectAudio, EffectConfig, EffectVerb
from engine.effects.builder import EffectBuilder

_AUDIO = EffectAudio(clips={{EffectVerb.START: AudioPlaybackConfig(name={clip!r}, loop=True)}})


class _Builder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        return Effect(name=name, pixels=None, audio=_AUDIO)


BUILD = _Builder()
"""

_A_WAV = Path(__file__).parents[3] / "packs/scenes/hardware_test/sounds/sfx_test_start.wav"
"""A real WAV for a card to carry: the simulated audio reads the length from its header."""


_REBOOT_ON_A_RULE = """\
from engine.engine import GameRule
from engine.input import InputEvents
from engine.state import GameState


class _Launch(GameRule):
    def __init__(self) -> None:
        self.on(InputEvents.Sensors, self._handle)

    def _handle(self, event: InputEvents.Sensors, state: GameState) -> None:
        if event.buttons.is_pressed("A"):
            state.scene_controls.reboot_into({target!r})


RULE = _Launch()
"""


def _package(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "__init__.py").touch()
    return directory


def _card_pack_dir(card: Path, kind: str, name: str) -> Path:
    """The package ``aura_packs/<kind>/<name>`` on *card*, made with every level above it."""
    return _package(_package(_package(card / "aura_packs") / kind) / name)


def install_card_scene(
    card: Path,
    scene: str,
    color: int = _GREEN,
    effect: str = "basic.solid",
    effect_pack: tuple[str, str] = ("basic", "1.1"),
) -> None:
    """Put *scene* on *card*: it lights the personal strip *color* with *effect*."""
    scene_dir = _card_pack_dir(card, "scenes", scene)
    (scene_dir / "scene.json").write_text(
        json.dumps(
            {
                "version": "1.0",
                "effect_packs": [{"name": effect_pack[0], "version": effect_pack[1]}],
                "rule_packs": [],
            }
        )
    )
    rules = _package(scene_dir / "rules")
    (rules / "light.py").write_text(_LIGHTING_RULE.format(effect=effect, color=color))


def install_card_scene_effect(
    card: Path, scene: str, effect: str, source: str = _SOLID_EFFECT
) -> None:
    """Give card scene *scene* its own effect *effect*, built by *source*."""
    effects = _package(_card_pack_dir(card, "scenes", scene) / "effects")
    (effects / f"{effect}.py").write_text(source)


def install_card_sound(owner_dir: Path, stem: str) -> None:
    """Put a playable ``<stem>.wav`` in the ``sounds/`` of the scene or pack at *owner_dir*."""
    sounds = owner_dir / "sounds"
    sounds.mkdir(parents=True, exist_ok=True)
    shutil.copy(_A_WAV, sounds / f"{stem}.wav")


def install_card_rule_pack(card: Path, pack: str, color: int = _GREEN) -> None:
    """Put rule pack *pack*, version 1.0, on *card*: its rule lights the personal strip *color*."""
    pack_dir = _card_pack_dir(card, "rules", pack)
    (pack_dir / "rules.json").write_text(json.dumps({"version": "1.0"}))
    (pack_dir / "light.py").write_text(_LIGHTING_RULE.format(effect="basic.solid", color=color))


def install_card_scene_using_rule_pack(card: Path, scene: str, pack: str) -> None:
    """Put *scene* on *card*: it has no rules of its own and runs rule pack *pack*, version 1.0."""
    scene_dir = _card_pack_dir(card, "scenes", scene)
    (scene_dir / "scene.json").write_text(
        json.dumps(
            {
                "version": "1.0",
                "effect_packs": [{"name": "basic", "version": "1.1"}],
                "rule_packs": [{"name": pack, "version": "1.0"}],
            }
        )
    )


def install_card_launcher(card: Path, scene: str, target: str) -> None:
    """Put *scene* on *card*: Button A reboots into *target*."""
    scene_dir = _card_pack_dir(card, "scenes", scene)
    (scene_dir / "scene.json").write_text(
        json.dumps({"version": "1.0", "effect_packs": [], "rule_packs": []})
    )
    rules = _package(scene_dir / "rules")
    (rules / "launch.py").write_text(_REBOOT_ON_A_RULE.format(target=target))


def install_card_effect_pack(card: Path, pack: str) -> None:
    """Put effect pack *pack*, version 1.0, on *card*: its ``solid`` lights every pixel."""
    pack_dir = _card_pack_dir(card, "effects", pack)
    (pack_dir / "effects.json").write_text(json.dumps({"version": "1.0"}))
    (pack_dir / "solid.py").write_text(_SOLID_EFFECT)


def lobby_of(*scenes: str) -> dict[str, dict]:
    """Setting overrides giving ``example_lobby`` *scenes* as its only entries."""
    entries = [
        {"scene": scene, "effect": "basic.solid", "options": {"color": _BLUE}} for scene in scenes
    ]
    return {"example_lobby": {"rule_packs": {"lobby": {"entries": entries}}}}


def test_a_device_reboots_into_a_card_scene_and_plays_it(simulation, tmp_path):
    install_card_scene(tmp_path, "card_scene")
    device = simulation.add_device(
        "red", scene="example_lobby", setting_overrides=lobby_of("card_scene"), card=tmp_path
    )

    device.tap("B")
    simulation.advance(0.1)

    assert device.scene == "card_scene"
    assert device.strip(Scope.PERSONAL).all_lit(_GREEN)


def test_a_device_handed_a_card_boots_into_its_card_scene_first_time(simulation, tmp_path):
    install_card_scene(tmp_path, "card_scene")

    device = simulation.add_device("red", scene="card_scene", card=tmp_path)
    simulation.advance(0.1)

    assert device.scene == "card_scene"
    assert device.strip(Scope.PERSONAL).all_lit(_GREEN)


def test_a_scene_using_a_card_effect_pack_plays_it(simulation, tmp_path):
    install_card_effect_pack(tmp_path, "card_pack")
    install_card_scene(
        tmp_path, "card_scene", effect="card_pack.solid", effect_pack=("card_pack", "1.0")
    )

    device = simulation.add_device("red", scene="card_scene", card=tmp_path)
    simulation.advance(0.1)

    assert device.strip(Scope.PERSONAL).all_lit(_GREEN)


def test_a_card_scenes_own_effect_plays(simulation, tmp_path):
    install_card_scene(tmp_path, "card_scene", effect="scene.glow")
    install_card_scene_effect(tmp_path, "card_scene", "glow")

    device = simulation.add_device("red", scene="card_scene", card=tmp_path)
    simulation.advance(0.1)

    assert device.strip(Scope.PERSONAL).all_lit(_GREEN)


def test_a_card_scenes_own_sound_plays_from_the_card(simulation, tmp_path):
    install_card_scene(tmp_path, "card_scene", effect="scene.chime")
    install_card_scene_effect(
        tmp_path, "card_scene", "chime", _CHIME_EFFECT.format(clip="scene.chime")
    )
    install_card_sound(_card_pack_dir(tmp_path, "scenes", "card_scene"), "chime")

    device = simulation.add_device("red", scene="card_scene", card=tmp_path)
    simulation.advance(0.1)

    assert device.is_playing("scene.chime")


def test_a_card_effect_packs_own_sound_plays_from_the_card(simulation, tmp_path):
    pack_dir = _card_pack_dir(tmp_path, "effects", "card_pack")
    (pack_dir / "effects.json").write_text(json.dumps({"version": "1.0"}))
    (pack_dir / "chime.py").write_text(_CHIME_EFFECT.format(clip="card_pack.chime"))
    install_card_sound(pack_dir, "chime")
    install_card_scene(
        tmp_path, "card_scene", effect="card_pack.chime", effect_pack=("card_pack", "1.0")
    )

    device = simulation.add_device("red", scene="card_scene", card=tmp_path)
    simulation.advance(0.1)

    assert device.is_playing("card_pack.chime")


def test_a_card_scene_runs_a_card_rule_packs_rule(simulation, tmp_path):
    install_card_rule_pack(tmp_path, "card_rules")
    install_card_scene_using_rule_pack(tmp_path, "card_scene", "card_rules")

    device = simulation.add_device("red", scene="card_scene", card=tmp_path)
    simulation.advance(0.1)

    assert device.strip(Scope.PERSONAL).all_lit(_GREEN)


def test_a_device_handed_a_card_without_aura_packs_boots_its_flash_scene(simulation, tmp_path):
    device = simulation.add_device("red", scene="element_browser", card=tmp_path)

    assert device.scene == "element_browser"


def test_a_device_handed_a_card_with_an_empty_aura_packs_boots_its_flash_scene(
    simulation, tmp_path
):
    _package(tmp_path / "aura_packs")

    device = simulation.add_device("red", scene="element_browser", card=tmp_path)

    assert device.scene == "element_browser"


def test_rebooting_into_a_scene_the_device_cannot_run_raises_and_persists_nothing(
    simulation, tmp_path
):
    install_card_launcher(tmp_path, "launcher", target="red_light_green_light")
    device = simulation.add_device(
        "red", scene="launcher", card=tmp_path, without={"accelerometer"}
    )
    state_file = tmp_path / "aura-state.json"
    before = state_file.read_text() if state_file.exists() else None

    with pytest.raises(MissingCapabilityError) as excinfo:
        device.tap("A")

    assert excinfo.value.scene == "red_light_green_light"
    assert (state_file.read_text() if state_file.exists() else None) == before


def test_a_refused_reboot_leaves_the_device_running_its_scene(simulation, tmp_path):
    install_card_launcher(tmp_path, "launcher", target="red_light_green_light")
    device = simulation.add_device(
        "red", scene="launcher", card=tmp_path, without={"accelerometer"}
    )

    with pytest.raises(MissingCapabilityError):
        device.tap("A")

    assert device.scene == "launcher"


def test_the_next_scene_a_device_persists_is_on_the_card_it_was_handed(simulation, tmp_path):
    device = simulation.add_device(
        "red", scene="example_lobby", setting_overrides=lobby_of("element_browser"), card=tmp_path
    )

    device.tap("B")

    assert json.loads((tmp_path / "aura-state.json").read_text())["scene"] == "element_browser"


def test_two_devices_handed_the_same_card_raise(simulation, tmp_path):
    simulation.add_device("red", scene="example_lobby", card=tmp_path)

    with pytest.raises(ValueError, match="red"):
        simulation.add_device("blue", scene="example_lobby", card=tmp_path)


def test_a_device_handed_another_devices_own_card_raises(simulation):
    red = simulation.add_device("red", scene="example_lobby")

    with pytest.raises(ValueError, match="red"):
        simulation.add_device("blue", scene="example_lobby", card=red.card)


def test_a_second_card_carrying_aura_packs_raises_naming_both_devices(simulation, tmp_path):
    red_card, blue_card = tmp_path / "red", tmp_path / "blue"
    install_card_scene(red_card, "card_scene")
    install_card_scene(blue_card, "card_scene")
    simulation.add_device("red", scene="card_scene", card=red_card)

    with pytest.raises(ValueError, match=r"blue.*red|red.*blue"):
        simulation.add_device("blue", scene="card_scene", card=blue_card)


def test_after_a_simulation_closes_a_card_scene_of_the_same_name_imports_from_its_own_card(
    tmp_path,
):
    first_card, second_card = tmp_path / "first", tmp_path / "second"
    install_card_scene(first_card, "card_scene", color=_GREEN)
    install_card_scene(second_card, "card_scene", color=_BLUE)
    with Simulation() as first:
        first.add_device("red", scene="card_scene", card=first_card)
        first.advance(0.1)

    with Simulation() as second:
        device = second.add_device("red", scene="card_scene", card=second_card)
        second.advance(0.1)

        assert device.strip(Scope.PERSONAL).all_lit(_BLUE)


def test_a_closed_simulation_leaves_no_card_pack_module_or_mount_root(tmp_path):
    install_card_scene(tmp_path / "handed", "card_scene")
    with Simulation() as simulation:
        device = simulation.add_device("red", scene="card_scene", card=tmp_path / "handed")

    assert not [name for name in sys.modules if name.split(".")[0] == "aura_packs"]
    assert str(device.card) not in sys.path


def test_closing_a_simulation_keeps_a_card_the_test_handed_it(tmp_path):
    install_card_scene(tmp_path, "card_scene")
    with Simulation() as simulation:
        simulation.add_device("red", scene="card_scene", card=tmp_path)

    assert (tmp_path / "aura_packs" / "scenes" / "card_scene" / "scene.json").is_file()

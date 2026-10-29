"""A Simulated device's card is a real directory: card scenes and card packs work as on a device."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from app.simulation import Simulation
from engine.state import Scope

_SCENES_DIR = Path(__file__).resolve().parents[3] / "packs" / "scenes"

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
from engine.effects.manager import EffectBuilder


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


def _package(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "__init__.py").touch()
    return directory


def install_card_scene(
    card: Path,
    scene: str,
    color: int = _GREEN,
    effect: str = "basic.solid",
    effect_pack: tuple[str, str] = ("basic", "1.1"),
) -> None:
    """Put *scene* on *card*: it lights the personal strip *color* with *effect*."""
    scene_dir = _package(_package(_package(card / "aura_packs") / "scenes") / scene)
    (scene_dir / "scene.json").write_text(
        json.dumps({"version": "1.0", "effect_packs": [list(effect_pack)], "rule_packs": []})
    )
    rules = _package(scene_dir / "rules")
    (rules / "light.py").write_text(_LIGHTING_RULE.format(effect=effect, color=color))


def install_card_effect_pack(card: Path, pack: str) -> None:
    """Put effect pack *pack*, version 1.0, on *card*: its ``solid`` lights every pixel."""
    pack_dir = _package(_package(_package(card / "aura_packs") / "effects") / pack)
    (pack_dir / "version.txt").write_text("1.0")
    (pack_dir / "solid.py").write_text(_SOLID_EFFECT)


def lobby_of(*scenes: str) -> dict[str, object]:
    """``example_lobby``'s tunables with *scenes* as its only entries."""
    lobby = json.loads((_SCENES_DIR / "example_lobby" / "scene.json").read_text())
    lobby = lobby["initial_data"]["lobby"]
    lobby["entries"] = [
        {"scene": scene, "effect": "basic.solid", "options": {"color": _BLUE}} for scene in scenes
    ]
    return {"lobby": lobby}


def test_a_device_reboots_into_a_card_scene_and_plays_it(simulation, tmp_path):
    install_card_scene(tmp_path, "card_scene")
    device = simulation.add_device(
        "red", scene="example_lobby", scene_data=lobby_of("card_scene"), card=tmp_path
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


def test_a_card_less_device_has_no_card_and_does_not_reboot(simulation):
    device = simulation.add_device(
        "red", scene="example_lobby", scene_data=lobby_of("element_browser"), sd_card=False
    )

    device.tap("B")

    assert device.card is None
    assert device.scene == "example_lobby"


def test_the_next_scene_a_device_persists_is_on_the_card_it_was_handed(simulation, tmp_path):
    device = simulation.add_device(
        "red", scene="example_lobby", scene_data=lobby_of("element_browser"), card=tmp_path
    )

    device.tap("B")

    assert json.loads((tmp_path / "aura-state.json").read_text())["scene"] == "element_browser"


def test_two_devices_handed_the_same_card_raise(simulation, tmp_path):
    simulation.add_device("red", scene="example_lobby", card=tmp_path)

    with pytest.raises(ValueError, match="red"):
        simulation.add_device("blue", scene="example_lobby", card=tmp_path)


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
        handed = simulation.add_device("red", scene="card_scene", card=tmp_path / "handed")
        own = simulation.add_device("blue", scene="example_lobby")
        mount_roots = {str(handed.card), str(own.card)}

    assert not [name for name in sys.modules if name.split(".")[0] == "aura_packs"]
    assert not mount_roots & set(sys.path)
    assert (tmp_path / "handed" / "aura_packs").is_dir()  # the test owns a card it handed over

"""A test can cover a simulated device's scene with an Overlay and pop it, as a pause would."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.simulation import TICK
from engine.capabilities import MissingCapabilityError
from engine.state import Scope

_RED = 0xFF0000
_GREEN = 0x00FF00
_BLUE = 0x0000FF

_TAP_COUNTER_RULE = """\
from engine.engine import GameRule
from engine.input import InputEvents
from engine.state import GameState, Scope

_COLORS = (0xFF0000, 0x00FF00, 0xFFFF00)


class _CountTaps(GameRule):
    def __init__(self) -> None:
        self.on(InputEvents.Sensors, self._handle)

    def _handle(self, event: InputEvents.Sensors, state: GameState) -> None:
        taps = state.get("taps", 0)
        if event.buttons.is_pressed("A"):
            taps += 1
            state.set("taps", taps)
        state.effect_controls.set_effect(
            Scope.PERSONAL, "basic.solid", {"color": _COLORS[min(taps, 2)]}
        )


RULE = _CountTaps()
"""

_PAUSE_RULE = """\
from engine.engine import GameRule
from engine.input import InputEvents
from engine.state import GameState, Scope


class _Paused(GameRule):
    def __init__(self) -> None:
        self.on(InputEvents.Sensors, self._handle)

    def _handle(self, event: InputEvents.Sensors, state: GameState) -> None:
        state.effect_controls.set_effect(Scope.PERSONAL, "basic.solid", {"color": 0x0000FF})


RULE = _Paused()
"""


def _package(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "__init__.py").touch()
    return directory


def _install_card_scene(card: Path, scene: str, rule: str) -> None:
    """Put *scene* on *card*, running the one rule module source *rule*."""
    scene_dir = _package(_package(_package(card / "aura_packs") / "scenes") / scene)
    (scene_dir / "scene.json").write_text(
        json.dumps(
            {
                "version": "1.0",
                "effect_packs": [{"name": "basic", "version": "1.1"}],
                "rule_packs": [],
            }
        )
    )
    (_package(scene_dir / "rules") / "rule.py").write_text(rule)


@pytest.fixture()
def card(tmp_path: Path) -> Path:
    """A card with ``counter`` (A taps step its light red, green, yellow) and ``pause`` (blue)."""
    _install_card_scene(tmp_path, "counter", _TAP_COUNTER_RULE)
    _install_card_scene(tmp_path, "pause", _PAUSE_RULE)
    return tmp_path


def test_while_covered_the_overlays_rules_run(simulation, card):
    device = simulation.add_device("red", scene="counter", card=card)
    simulation.advance(0.1)

    device.overlay("pause")
    simulation.advance(0.1)

    assert device.strip(Scope.PERSONAL).all_lit(_BLUE)


def test_after_pop_the_covered_scenes_rules_run_again_with_its_game_state_kept(simulation, card):
    device = simulation.add_device("red", scene="counter", card=card)
    device.tap("A")
    device.overlay("pause")
    simulation.advance(0.1)

    device.pop()
    simulation.advance(0.1)

    assert device.strip(Scope.PERSONAL).all_lit(_GREEN)


def test_while_covered_the_covered_scenes_rules_do_not_run(simulation, card):
    device = simulation.add_device("red", scene="counter", card=card)
    device.overlay("pause")
    simulation.advance(0.1)

    device.tap("A")
    device.pop()
    simulation.advance(0.1)

    assert device.strip(Scope.PERSONAL).all_lit(_RED)


def test_an_overlay_takes_effect_at_the_end_of_the_next_tick(simulation, card):
    device = simulation.add_device("red", scene="counter", card=card)
    simulation.advance(0.1)

    device.overlay("pause")
    simulation.advance(TICK)
    lit_on_the_overlays_own_tick = device.strip(Scope.PERSONAL).all_lit(_BLUE)
    simulation.advance(TICK)

    assert not lit_on_the_overlays_own_tick
    assert device.strip(Scope.PERSONAL).all_lit(_BLUE)


def test_a_pop_takes_effect_at_the_end_of_the_next_tick(simulation, card):
    device = simulation.add_device("red", scene="counter", card=card)
    device.overlay("pause")
    simulation.advance(0.1)

    device.pop()
    simulation.advance(TICK)
    lit_on_the_pops_own_tick = device.strip(Scope.PERSONAL).all_lit(_RED)
    simulation.advance(TICK)

    assert not lit_on_the_pops_own_tick
    assert device.strip(Scope.PERSONAL).all_lit(_RED)


def test_covering_with_a_scene_the_device_cannot_run_raises(simulation, card):
    device = simulation.add_device("red", scene="counter", card=card, without={"accelerometer"})

    with pytest.raises(MissingCapabilityError) as excinfo:
        device.overlay("red_light_green_light")

    assert excinfo.value.scene == "red_light_green_light"


def test_a_refused_overlay_leaves_the_running_scene_uncovered(simulation, card):
    device = simulation.add_device("red", scene="counter", card=card, without={"accelerometer"})
    with pytest.raises(MissingCapabilityError):
        device.overlay("red_light_green_light")

    device.tap("A")
    simulation.advance(0.1)

    assert device.scene == "counter"
    assert device.strip(Scope.PERSONAL).all_lit(_GREEN)

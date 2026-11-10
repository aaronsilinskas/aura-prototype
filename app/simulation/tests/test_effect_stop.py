"""A looping sound ends with its effect when a rule stops or replaces it (#1198)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.simulation import TICK, SimulatedDevice, Simulation

_HUM = "basic.blip_echo"
"""``scene.hum``'s looping clip."""

_STING = "basic.game_over_sting_start"
"""``scene.sting``'s one-shot ``START`` clip."""

_HUM_UNTIL_A_RULE = """\
from engine.engine import GameRule
from engine.input import InputEvents
from engine.state import GameState, Scope


class _HumUntilA(GameRule):
    def __init__(self) -> None:
        self.on(InputEvents.Sensors, self._handle)

    def _handle(self, event: InputEvents.Sensors, state: GameState) -> None:
        if not state.get("humming", False):
            state.set("humming", True)
            state.effect_controls.set_effect(Scope.ALL, "scene.hum", {{}})
        elif event.buttons.is_pressed("A") and not state.get("pressed", False):
            state.set("pressed", True)
            {on_press}


RULE = _HumUntilA()
"""

_STOP = "state.effect_controls.stop_effect(Scope.ALL)"
_REPLACE = 'state.effect_controls.set_effect(Scope.ALL, "scene.sting", {})'


def _audio_effect(clip: str, *, loop: bool) -> str:
    return f"""\
from effects.effect import AudioPlaybackConfig, Effect, EffectAudio, EffectConfig, EffectVerb
from engine.effects.builder import EffectBuilder

_AUDIO = EffectAudio(
    clips={{EffectVerb.START: AudioPlaybackConfig(name={clip!r}, loop={loop!r})}}
)


class _Builder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        return Effect(name=name, audio=_AUDIO)


BUILD = _Builder()
"""


def _package(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "__init__.py").touch()
    return directory


def _install_card_scene(card: Path, scene: str, on_press: str) -> None:
    """Put *scene* on *card*: it starts ``scene.hum`` and runs *on_press* on the first A press."""
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
    (_package(scene_dir / "rules") / "rule.py").write_text(
        _HUM_UNTIL_A_RULE.format(on_press=on_press)
    )
    effects = _package(scene_dir / "effects")
    (effects / "hum.py").write_text(_audio_effect(_HUM, loop=True))
    (effects / "sting.py").write_text(_audio_effect(_STING, loop=False))


@pytest.fixture()
def card(tmp_path: Path) -> Path:
    """A card whose scenes hum until A is pressed.

    Then ``stop`` stops ``Scope.ALL``, and ``replace`` sets ``scene.sting`` there.
    """
    _install_card_scene(tmp_path, "stop", _STOP)
    _install_card_scene(tmp_path, "replace", _REPLACE)
    return tmp_path


def _hum_then_press_a(simulation: Simulation, card: Path, scene: str) -> SimulatedDevice:
    device = simulation.add_device("red", scene=scene, card=card)
    simulation.advance(0.1)
    assert device.is_playing(_HUM)
    device.hold("A")
    return device


def test_stopping_a_looping_effects_scope_silences_its_loop_the_next_tick(simulation, card):
    device = _hum_then_press_a(simulation, card, "stop")

    simulation.advance(TICK)

    assert not device.is_playing(_HUM)


def test_replacing_a_looping_effect_silences_its_loop_the_next_tick(simulation, card):
    device = _hum_then_press_a(simulation, card, "replace")

    simulation.advance(TICK)

    assert not device.is_playing(_HUM)


def test_the_replacing_effects_start_clip_still_plays(simulation, card):
    device = _hum_then_press_a(simulation, card, "replace")

    simulation.advance(TICK)

    assert device.is_playing(_STING)

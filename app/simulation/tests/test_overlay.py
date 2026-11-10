"""A test can cover a simulated device's scene with an Overlay and pop it, as a pause would."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.simulation import TICK, SimulatedDevice, Simulation
from engine.capabilities import MissingCapabilityError
from engine.network import LINE
from engine.pack_catalog import SettingOverrides
from engine.state import Scope
from packs.scenes.tag.tag_data import TagData, encode_tag_data

_RED = 0xFF0000
_GREEN = 0x00FF00

# _SHOOTER, _tag and _start_tag copy Tag's test helpers: the harness's tests
# stand on no scene's tests.
_SHOOTER: dict[str, object] = {"expected_team": 2, "expected_player": 3}
"""The team/player a Tag device both fires as and counts hits from."""


def _tag(settings: dict[str, object]) -> SettingOverrides:
    return {"tag": {"settings": settings}}


def _start_tag(simulation: Simulation, *players: SimulatedDevice) -> None:
    for player in players:
        player.tap("A")
    simulation.run_until(lambda: all(p.has_played("scene.go_start") for p in players))
    for player in players:
        player.forget()


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


_GLOW_ONCE_RULE = """\
from engine.engine import GameRule
from engine.input import InputEvents
from engine.state import GameState, Scope


class _GlowOnce(GameRule):
    def __init__(self) -> None:
        self.on(InputEvents.Sensors, self._handle)

    def _handle(self, event: InputEvents.Sensors, state: GameState) -> None:
        if not state.get("lit", False):
            state.set("lit", True)
            state.effect_controls.set_effect(Scope.PERSONAL, "basic.solid", {"color": 0xFF0000})


RULE = _GlowOnce()
"""

_IDLE_RULE = """\
from engine.engine import GameRule

RULE = GameRule()
"""

_GREEN_ON_IR_RULE = """\
from engine.engine import GameRule
from engine.network import NetworkEvents
from engine.state import GameState, Scope


class _GreenOnIr(GameRule):
    def __init__(self) -> None:
        self.on(NetworkEvents.IRReceived, self._handle)

    def _handle(self, event: NetworkEvents.IRReceived, state: GameState) -> None:
        state.effect_controls.set_effect(Scope.PERSONAL, "basic.solid", {"color": 0x00FF00})


RULE = _GreenOnIr()
"""


_HUM_ONCE_RULE = """\
from engine.engine import GameRule
from engine.input import InputEvents
from engine.state import GameState, Scope


class _HumOnce(GameRule):
    def __init__(self) -> None:
        self.on(InputEvents.Sensors, self._handle)

    def _handle(self, event: InputEvents.Sensors, state: GameState) -> None:
        if not state.get("humming", False):
            state.set("humming", True)
            state.effect_controls.set_effect(Scope.ALL, "scene.hum", {})


RULE = _HumOnce()
"""

_HUM_EFFECT = """\
from effects.effect import AudioPlaybackConfig, Effect, EffectAudio, EffectConfig, EffectVerb
from engine.effects.builder import EffectBuilder

_AUDIO = EffectAudio(
    clips={EffectVerb.START: AudioPlaybackConfig(name="basic.blip_echo", loop=True)}
)


class _Builder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        return Effect(name=name, audio=_AUDIO)


BUILD = _Builder()
"""

_HUM = "basic.blip_echo"
"""``hum``'s looping clip; a shared pack clip, so it resolves the same under the overlay."""


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
    """A card with these scenes, all on the default Aura IR codec.

    ``counter``: A taps step its light red, green, yellow, re-set every tick.
    ``pause``: blue every tick. ``glow``: red, set once. ``idle``: does
    nothing. ``listen``: green once an IR shot is decoded. ``hum``: starts
    a looping sound, once.
    """
    _install_card_scene(tmp_path, "counter", _TAP_COUNTER_RULE)
    _install_card_scene(tmp_path, "pause", _PAUSE_RULE)
    _install_card_scene(tmp_path, "glow", _GLOW_ONCE_RULE)
    _install_card_scene(tmp_path, "idle", _IDLE_RULE)
    _install_card_scene(tmp_path, "listen", _GREEN_ON_IR_RULE)
    _install_card_scene(tmp_path, "hum", _HUM_ONCE_RULE)
    (_package(tmp_path / "aura_packs" / "scenes" / "hum" / "effects") / "hum.py").write_text(
        _HUM_EFFECT
    )
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
    # The covered scene's held light is given back as the pop applies, so it
    # shows on the pop's own tick; the pop's call alone changes nothing.
    device = simulation.add_device("red", scene="counter", card=card)
    simulation.advance(0.1)
    device.overlay("pause")
    simulation.advance(0.1)

    device.pop()
    lit_before_the_next_tick = device.strip(Scope.PERSONAL).all_lit(_BLUE)
    simulation.advance(TICK)

    assert lit_before_the_next_tick
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


# ---------------------------------------------------------------------------
# The covered scene's effects are set aside and given back (#1194)
# ---------------------------------------------------------------------------


def test_while_covered_the_covered_scenes_lights_go_dark(simulation, card):
    device = simulation.add_device("red", scene="glow", card=card)
    simulation.advance(0.1)

    device.overlay("idle")
    simulation.advance(0.1)

    assert device.strip(Scope.PERSONAL).dark


def test_after_pop_the_covered_scenes_lights_come_back_without_being_set_again(simulation, card):
    device = simulation.add_device("red", scene="glow", card=card)
    simulation.advance(0.1)
    device.overlay("idle")
    simulation.advance(0.1)

    device.pop()
    simulation.advance(0.1)

    assert device.strip(Scope.PERSONAL).all_lit(_RED)


def test_while_covering_tag_an_overlay_hears_shots_in_tags_codec(simulation, card):
    red = simulation.add_device("red", scene="tag", card=card, setting_overrides=_tag(_SHOOTER))
    blue = simulation.add_device("blue", scene="tag", setting_overrides=_tag(_SHOOTER))
    _start_tag(simulation, red, blue)
    red.overlay("listen")  # declares the Aura codec
    simulation.advance(0.1)

    blue.aim(LINE, at=red)
    blue.tap("A")
    simulation.advance(0.1)

    assert red.strip(Scope.PERSONAL).all_lit(_GREEN)


def test_after_an_overlay_is_popped_tag_still_decodes_shots(simulation, card):
    red = simulation.add_device("red", scene="tag", card=card, setting_overrides=_tag(_SHOOTER))
    blue = simulation.add_device("blue", scene="tag", setting_overrides=_tag(_SHOOTER))
    _start_tag(simulation, red, blue)
    red.overlay("listen")
    simulation.advance(0.1)
    red.pop()
    simulation.advance(0.1)

    blue.aim(LINE, at=red)
    blue.tap("A")
    simulation.advance(0.1)

    assert red.has_played("scene.hit_start")


# ---------------------------------------------------------------------------
# The covered scene's sound falls silent and comes back (#1195)
# ---------------------------------------------------------------------------

_STING = "basic.game_over_sting_start"
"""Tag's game-over sting: a ``stops_effect`` one-shot whose end returns Tag to Ready."""

_SHOOTER_SHOT = bytes(encode_tag_data(TagData(2, 3, 1)))
"""A one-damage tag shot from ``_SHOOTER``."""


def _lose_tag(simulation: Simulation, player: SimulatedDevice) -> None:
    """Land the one hit a one-hitpoint *player* can take, and run until its sting starts."""
    player.receive_ir(_SHOOTER_SHOT)
    simulation.run_until(lambda: player.has_played(_STING))


def test_while_covered_the_covered_scenes_one_shot_falls_silent(simulation, card):
    player = simulation.add_device(
        "red", scene="tag", card=card, setting_overrides=_tag({**_SHOOTER, "starting_hitpoints": 1})
    )
    _start_tag(simulation, player)
    _lose_tag(simulation, player)

    player.overlay("idle")
    simulation.advance(0.1)

    assert not player.is_playing(_STING)


def test_a_tag_game_paused_during_its_game_over_sting_finishes_game_over_after_pop(
    simulation, card
):
    # The cut-off sting counts as finished, so its game over ends as soon as
    # play resumes rather than waiting on a sound that will never play out.
    player = simulation.add_device(
        "red", scene="tag", card=card, setting_overrides=_tag({**_SHOOTER, "starting_hitpoints": 1})
    )
    _start_tag(simulation, player)
    _lose_tag(simulation, player)
    player.overlay("idle")
    simulation.advance(0.1)

    player.pop()
    simulation.advance(0.1)

    assert player.has_played("scene.ready_shots_start")
    assert not player.is_playing(_STING), "a cut-off one-shot is not replayed"


def test_while_covered_the_covered_scenes_looping_sound_is_silent(simulation, card):
    device = simulation.add_device("red", scene="hum", card=card)
    simulation.advance(0.1)
    humming = device.is_playing(_HUM)

    device.overlay("idle")
    simulation.advance(0.1)

    assert humming
    assert not device.is_playing(_HUM)


def test_after_pop_the_covered_scenes_looping_sound_plays_again(simulation, card):
    device = simulation.add_device("red", scene="hum", card=card)
    simulation.advance(0.1)
    device.overlay("idle")
    simulation.advance(0.1)

    device.pop()
    simulation.advance(0.1)

    assert device.is_playing(_HUM)

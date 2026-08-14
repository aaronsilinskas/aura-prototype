"""Tests for TagShootingRule — Button-A firing and fire-shot feedback."""

from __future__ import annotations

import pytest

from engine.engine import GameEngine
from engine.input import ButtonData, InputEvents
from engine.network import LINE
from engine.state import EffectReceipt, GameState, SceneControls, Scope
from engine.tests.helpers import SpyEffectControls, SpyNetworkControls
from hardware.shared.tag_protocol import TagData, encode_tag_data
from packs.scenes.tag.rules.helpers.phases import PHASE_PLAYING, PHASE_READY
from packs.scenes.tag.rules.helpers.tag_state import tag_state
from packs.scenes.tag.rules.shooting_rule import TagShootingRule
from packs.scenes.tag.rules.tests.helpers import StubTimer, seed_phase


@pytest.fixture()
def spy() -> SpyEffectControls:
    return SpyEffectControls()


def _make_state(
    spy: SpyEffectControls,
    initial_data: dict | None = None,
    network_spy: SpyNetworkControls | None = None,
) -> tuple[GameState, GameEngine, StubTimer]:
    timer = StubTimer()
    engine = GameEngine(spy, network_controls=network_spy, timer=timer)  # pyright: ignore
    engine.add_rules(TagShootingRule())
    state = engine.create_state(SceneControls(), initial_data=initial_data or {})
    tag = seed_phase(state, PHASE_PLAYING, entered=True)
    tag.shot.ammo = 10
    return state, engine, timer


def _tick(
    state: GameState,
    engine: GameEngine,
    timer: StubTimer,
    total: float,
    button_a: bool | int = False,
) -> None:
    timer.total = total
    states: dict[str, int] = {}
    if button_a is True:
        states["A"] = ButtonData.PRESSED
    elif button_a is not False:
        states["A"] = button_a
    state.queue_event(InputEvents.Sensors(ButtonData(states=states)))
    engine.update(state)


def test_button_a_sends_tag_data_payload_on_line_emitter(spy):
    network_spy = SpyNetworkControls()
    state, engine, timer = _make_state(spy, network_spy=network_spy)

    _tick(state, engine, timer, 0.0, button_a=True)

    expected_payload = bytes(encode_tag_data(TagData(0, 1, 1)))
    assert network_spy.send_ir_calls == [(expected_payload, LINE)]


def test_button_a_logs_the_send(spy, capsys):
    network_spy = SpyNetworkControls()
    state, engine, timer = _make_state(spy, network_spy=network_spy)

    _tick(state, engine, timer, 0.0, button_a=True)

    assert "sending IR packet" in capsys.readouterr().out


def test_button_a_plays_fire_shot_effect_on_directional(spy):
    network_spy = SpyNetworkControls()
    state, engine, timer = _make_state(spy, network_spy=network_spy)

    _tick(state, engine, timer, 0.0, button_a=True)

    fire_calls = [c for c in spy.set_effect_calls if c[1] == "scene.fire_shot"]
    assert len(fire_calls) == 1
    scope, _, _ = fire_calls[0]
    assert scope is Scope.DIRECTIONAL


def test_no_button_press_does_not_fire(spy):
    network_spy = SpyNetworkControls()
    state, engine, timer = _make_state(spy, network_spy=network_spy)

    _tick(state, engine, timer, 0.0)

    assert network_spy.send_ir_calls == []
    assert spy.set_effect_calls == []


def test_non_playing_phase_is_ignored(spy):
    network_spy = SpyNetworkControls()
    state, engine, timer = _make_state(spy, network_spy=network_spy)
    seed_phase(state, PHASE_READY, entered=True)

    _tick(state, engine, timer, 0.0, button_a=True)

    assert network_spy.send_ir_calls == []
    assert spy.set_effect_calls == []


def test_firing_decrements_ammo(spy):
    network_spy = SpyNetworkControls()
    state, engine, timer = _make_state(spy, network_spy=network_spy)

    _tick(state, engine, timer, 0.0, button_a=True)

    assert tag_state(state).shot.ammo == 10 - 1


def test_firing_stamps_last_shot_at(spy):
    network_spy = SpyNetworkControls()
    state, engine, timer = _make_state(spy, network_spy=network_spy)

    _tick(state, engine, timer, 5.0, button_a=True)

    assert tag_state(state).shot.last_shot_at == pytest.approx(5.0)


def test_firing_reissues_amber_ammo_bar_on_global_buff_when_ammo_remains(spy):
    network_spy = SpyNetworkControls()
    state, engine, timer = _make_state(spy, network_spy=network_spy)

    _tick(state, engine, timer, 0.0, button_a=True)

    progress_calls = [c for c in spy.set_effect_calls if c[1] == "basic.progress"]
    buff_calls = [c for c in progress_calls if c[0] is Scope.Global.BUFF]
    assert len(buff_calls) == 1
    _, _, options = buff_calls[0]
    expected_fraction = (10 - 1) / 10
    assert options == {"progress": pytest.approx(expected_fraction), "color": 0xFFBF00}


def test_firing_the_last_shot_sets_ammo_empty_pulse_on_global_buff(spy):
    network_spy = SpyNetworkControls()
    state, engine, timer = _make_state(spy, network_spy=network_spy)
    tag_state(state).shot.ammo = 1

    _tick(state, engine, timer, 0.0, button_a=True)  # fires the last shot, ammo -> 0

    assert tag_state(state).shot.ammo == 0
    empty_calls = [c for c in spy.set_effect_calls if c[1] == "scene.ammo_empty"]
    assert len(empty_calls) == 1
    scope, _, _ = empty_calls[0]
    assert scope is Scope.Global.BUFF
    progress_calls = [c for c in spy.set_effect_calls if c[1] == "basic.progress"]
    assert progress_calls == []


def test_second_shot_within_cooldown_is_blocked(spy):
    network_spy = SpyNetworkControls()
    state, engine, timer = _make_state(spy, network_spy=network_spy)

    _tick(state, engine, timer, 0.0, button_a=True)
    _tick(state, engine, timer, 0.2, button_a=True)

    assert len(network_spy.send_ir_calls) == 1
    assert tag_state(state).shot.ammo == 10 - 1


def test_shot_after_cooldown_interval_is_allowed(spy):
    network_spy = SpyNetworkControls()
    state, engine, timer = _make_state(spy, network_spy=network_spy)

    _tick(state, engine, timer, 0.0, button_a=True)
    _tick(state, engine, timer, 1.0, button_a=True)

    assert len(network_spy.send_ir_calls) == 2
    assert tag_state(state).shot.ammo == 10 - 2


def test_pressing_with_no_ammo_does_not_fire(spy):
    network_spy = SpyNetworkControls()
    state, engine, timer = _make_state(spy, network_spy=network_spy)
    tag_state(state).shot.ammo = 0

    _tick(state, engine, timer, 0.0, button_a=True)

    assert network_spy.send_ir_calls == []


# ---------------------------------------------------------------------------
# Reload start
# ---------------------------------------------------------------------------


def test_fresh_press_with_no_ammo_starts_reload(spy):
    network_spy = SpyNetworkControls()
    state, engine, timer = _make_state(spy, network_spy=network_spy)
    tag_state(state).shot.ammo = 0

    _tick(state, engine, timer, 2.0, button_a=True)

    assert tag_state(state).shot.reload_started_at == pytest.approx(2.0)
    reload_calls = [c for c in spy.set_effect_calls if c[1] == "scene.reload"]
    assert len(reload_calls) == 1
    scope, _, options = reload_calls[0]
    assert scope is Scope.Global.BUFF
    assert options == {"duration": pytest.approx(3.0)}


def test_fresh_press_with_no_ammo_adds_dry_fire_feedback(spy):
    network_spy = SpyNetworkControls()
    state, engine, timer = _make_state(spy, network_spy=network_spy)
    tag_state(state).shot.ammo = 0

    _tick(state, engine, timer, 2.0, button_a=True)

    dry_fire_calls = [c for c in spy.add_effect_calls if c[1] == "scene.dry_fire"]
    assert len(dry_fire_calls) == 1
    scope, _, _ = dry_fire_calls[0]
    assert scope is Scope.DIRECTIONAL


def test_held_trigger_from_emptying_shot_does_not_start_reload(spy):
    """The tick that empties the magazine is a fresh PRESSED; the next held
    tick is DOWN, not PRESSED, so it must not start a reload."""
    network_spy = SpyNetworkControls()
    state, engine, timer = _make_state(spy, network_spy=network_spy)
    tag_state(state).shot.ammo = 1

    _tick(state, engine, timer, 0.0, button_a=True)  # fires the last shot, ammo -> 0

    assert tag_state(state).shot.ammo == 0
    reload_calls = [c for c in spy.set_effect_calls if c[1] == "scene.reload"]
    assert reload_calls == []
    assert tag_state(state).shot.reload_started_at is None


def test_reload_start_is_not_gated_by_cooldown(spy):
    network_spy = SpyNetworkControls()
    state, engine, timer = _make_state(spy, network_spy=network_spy)
    tag = tag_state(state)
    tag.shot.ammo = 0
    tag.shot.last_shot_at = 0.0  # cooldown would otherwise block until shot_cooldown elapses

    _tick(state, engine, timer, 0.01, button_a=True)

    assert tag_state(state).shot.reload_started_at == pytest.approx(0.01)


# ---------------------------------------------------------------------------
# Reload hold / complete
# ---------------------------------------------------------------------------


def test_holding_to_reload_duration_restores_ammo_to_max(spy):
    network_spy = SpyNetworkControls()
    state, engine, timer = _make_state(spy, network_spy=network_spy)
    tag = tag_state(state)
    tag.shot.ammo = 0
    tag.shot.reload_started_at = 0.0
    tag.shot.reload_receipt = EffectReceipt(0)

    _tick(state, engine, timer, 3.0, button_a=ButtonData.DOWN)  # held, total - start >= 3.0

    assert tag_state(state).shot.ammo == 10


def test_completing_reload_snaps_amber_ammo_bar_full_via_basic_progress(spy):
    network_spy = SpyNetworkControls()
    state, engine, timer = _make_state(spy, network_spy=network_spy)
    tag = tag_state(state)
    tag.shot.ammo = 0
    tag.shot.reload_started_at = 0.0
    tag.shot.reload_receipt = EffectReceipt(0)

    _tick(state, engine, timer, 3.0, button_a=ButtonData.DOWN)

    progress_calls = [c for c in spy.set_effect_calls if c[1] == "basic.progress"]
    buff_calls = [c for c in progress_calls if c[0] is Scope.Global.BUFF]
    assert len(buff_calls) == 1
    _, _, options = buff_calls[0]
    assert options == {"progress": pytest.approx(1.0), "color": 0xFFBF00}


def test_completing_reload_adds_reload_complete_effect(spy):
    network_spy = SpyNetworkControls()
    state, engine, timer = _make_state(spy, network_spy=network_spy)
    tag = tag_state(state)
    tag.shot.ammo = 0
    tag.shot.reload_started_at = 0.0
    tag.shot.reload_receipt = EffectReceipt(0)

    _tick(state, engine, timer, 3.0, button_a=ButtonData.DOWN)

    complete_calls = [c for c in spy.add_effect_calls if c[1] == "scene.reload_complete"]
    assert len(complete_calls) == 1
    scope, _, _ = complete_calls[0]
    assert scope is Scope.Global.BUFF


def test_completing_reload_clears_reload_started_at(spy):
    network_spy = SpyNetworkControls()
    state, engine, timer = _make_state(spy, network_spy=network_spy)
    tag = tag_state(state)
    tag.shot.ammo = 0
    tag.shot.reload_started_at = 0.0
    tag.shot.reload_receipt = EffectReceipt(0)

    _tick(state, engine, timer, 3.0, button_a=ButtonData.DOWN)

    assert tag_state(state).shot.reload_started_at is None


def test_held_trigger_after_completion_does_not_auto_fire(spy):
    network_spy = SpyNetworkControls()
    state, engine, timer = _make_state(spy, network_spy=network_spy)
    tag = tag_state(state)
    tag.shot.ammo = 0
    tag.shot.reload_started_at = 0.0
    tag.shot.reload_receipt = EffectReceipt(0)

    _tick(state, engine, timer, 3.0, button_a=ButtonData.DOWN)  # completes reload
    _tick(state, engine, timer, 3.0, button_a=ButtonData.DOWN)  # still held

    assert network_spy.send_ir_calls == []
    assert tag_state(state).shot.ammo == 10


# ---------------------------------------------------------------------------
# Reload cancel
# ---------------------------------------------------------------------------


def test_releasing_before_reload_completion_restores_ammo_empty_pulse(spy):
    network_spy = SpyNetworkControls()
    state, engine, timer = _make_state(spy, network_spy=network_spy)
    tag = tag_state(state)
    tag.shot.ammo = 0
    tag.shot.reload_started_at = 0.0
    tag.shot.reload_receipt = EffectReceipt(0)

    _tick(state, engine, timer, 1.0)  # release before the 3.0s duration elapses

    empty_calls = [c for c in spy.set_effect_calls if c[1] == "scene.ammo_empty"]
    buff_calls = [c for c in empty_calls if c[0] is Scope.Global.BUFF]
    assert len(buff_calls) == 1
    progress_calls = [c for c in spy.set_effect_calls if c[1] == "basic.progress"]
    assert progress_calls == []


def test_releasing_before_reload_completion_clears_reload_started_at(spy):
    network_spy = SpyNetworkControls()
    state, engine, timer = _make_state(spy, network_spy=network_spy)
    tag = tag_state(state)
    tag.shot.ammo = 0
    tag.shot.reload_started_at = 0.0
    tag.shot.reload_receipt = EffectReceipt(0)

    _tick(state, engine, timer, 1.0)

    assert tag_state(state).shot.reload_started_at is None
    assert tag_state(state).shot.ammo == 0


def test_releasing_before_reload_completion_does_not_add_reload_complete(spy):
    network_spy = SpyNetworkControls()
    state, engine, timer = _make_state(spy, network_spy=network_spy)
    tag = tag_state(state)
    tag.shot.ammo = 0
    tag.shot.reload_started_at = 0.0
    tag.shot.reload_receipt = EffectReceipt(0)

    _tick(state, engine, timer, 1.0)

    assert spy.add_effect_calls == []


# ---------------------------------------------------------------------------
# Completion precedence and firing suppression
# ---------------------------------------------------------------------------


def test_reaching_duration_threshold_on_release_tick_completes_not_cancels(spy):
    network_spy = SpyNetworkControls()
    state, engine, timer = _make_state(spy, network_spy=network_spy)
    tag = tag_state(state)
    tag.shot.ammo = 0
    tag.shot.reload_started_at = 0.0
    tag.shot.reload_receipt = EffectReceipt(0)

    _tick(state, engine, timer, 3.0)  # released, but threshold met on this tick

    assert tag_state(state).shot.ammo == 10
    progress_calls = [c for c in spy.set_effect_calls if c[1] == "basic.progress"]
    buff_calls = [c for c in progress_calls if c[0] is Scope.Global.BUFF]
    _, _, options = buff_calls[0]
    assert options == {"progress": pytest.approx(1.0), "color": 0xFFBF00}


def test_firing_is_suppressed_while_reloading(spy):
    network_spy = SpyNetworkControls()
    state, engine, timer = _make_state(spy, network_spy=network_spy)
    tag = tag_state(state)
    tag.shot.ammo = 0
    tag.shot.reload_started_at = 0.0
    tag.shot.reload_receipt = EffectReceipt(0)

    _tick(state, engine, timer, 1.0, button_a=ButtonData.DOWN)  # still mid-reload, held

    assert network_spy.send_ir_calls == []

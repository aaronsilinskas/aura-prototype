"""Spy-level tests for TagShootingRule edge cases the simulation can't pin to a tick.

Shooting behaviour is specified on simulated devices in
``packs/scenes/tag/tests/test_shooting.py``.
"""

from __future__ import annotations

import pytest

from engine.engine import GameEngine
from engine.input import ButtonData, InputEvents
from engine.state import EffectReceipt, SceneControls, Scope
from engine.tests.helpers import SpyEffectControls, SpyNetworkControls
from packs.scenes.tag.rules.helpers.phases import PHASE_PLAYING
from packs.scenes.tag.rules.helpers.tag_state import tag_state
from packs.scenes.tag.rules.shooting_rule import TagShootingRule
from packs.scenes.tag.rules.tests.helpers import StubTimer, seed_phase


def test_reaching_duration_threshold_on_release_tick_completes_not_cancels():
    spy = SpyEffectControls()
    timer = StubTimer()
    engine = GameEngine(spy, network_controls=SpyNetworkControls(), timer=timer)  # pyright: ignore
    engine.add_rules(TagShootingRule())
    state = engine.create_state(SceneControls(), initial_data={})
    tag = seed_phase(state, PHASE_PLAYING, entered=True)
    tag.shot.ammo = 0
    tag.shot.reload_started_at = 0.0
    tag.shot.reload_receipt = EffectReceipt(0)

    timer.total = 3.0  # the trigger is released on the very tick the reload completes
    state.queue_event(InputEvents.Sensors(ButtonData(states={})))
    engine.update(state)

    assert tag_state(state).shot.ammo == 10
    progress_calls = [c for c in spy.set_effect_calls if c[1] == "basic.progress"]
    buff_calls = [c for c in progress_calls if c[0] is Scope.Global.BUFF]
    _, _, options = buff_calls[0]
    assert options == {"progress": pytest.approx(1.0), "color": 0xFFBF00}

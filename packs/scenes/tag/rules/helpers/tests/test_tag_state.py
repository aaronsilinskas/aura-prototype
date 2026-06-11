"""Tests for the residual ``TagState`` and its ``tag_state`` accessor.

Phase mechanics now live in the scene's :class:`PhaseMachine` (covered by
``engine.tests.test_phase``); what remains here is the flat gameplay state:
hitpoints, the deafen deadline, and the per-phase receipts.
"""

from __future__ import annotations

from engine.engine import GameEngine
from engine.state import SceneControls
from engine.tests.helpers import SpyEffectControls
from packs.scenes.tag.rules.helpers.tag_state import TagState, tag_state


class _StubTimer:
    def __init__(self) -> None:
        self.elapsed: float = 0.0
        self.total: float = 0.0

    def update(self) -> None:
        pass


def _make_state(initial_data: dict | None = None):
    spy = SpyEffectControls()
    timer = _StubTimer()
    engine = GameEngine(spy, timer=timer)  # pyright: ignore[reportArgumentType]
    return engine.create_state(SceneControls(), initial_data=initial_data or {})


# ---------------------------------------------------------------------------
# Construction defaults
# ---------------------------------------------------------------------------


def test_new_tag_state_starts_with_zeroed_gameplay_fields():
    tag = TagState()

    assert tag.hitpoints == 0
    assert tag.deafen_until == 0.0


def test_new_tag_state_has_no_receipts():
    tag = TagState()

    assert tag.progress_receipt is None
    assert tag.warning_receipt is None
    assert tag.game_over_receipt is None


# ---------------------------------------------------------------------------
# tag_state — get-or-create accessor
# ---------------------------------------------------------------------------


def test_tag_state_caches_the_same_instance_across_calls():
    state = _make_state()

    first = tag_state(state)
    second = tag_state(state)

    assert first is second


def test_tag_state_mutations_persist_across_accessor_calls():
    state = _make_state()

    tag_state(state).hitpoints = 7

    assert tag_state(state).hitpoints == 7

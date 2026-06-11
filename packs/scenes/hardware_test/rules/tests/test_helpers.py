"""Tests for the hw_test rules/helpers subpackage."""

from __future__ import annotations

import pytest

from engine.state import EffectReceipt, GameState, SceneControls
from engine.tests.helpers import SpyEffectControls
from packs.scenes.hardware_test.rules.helpers.flash import Flash
from packs.scenes.hardware_test.rules.helpers.phases import (
    MODE_ACCELEROMETER,
    MODE_IR,
    MODE_ORDER,
    MODE_RADIO,
    MODE_RGB,
    MODE_SFX,
    next_in_cycle,
)


@pytest.fixture()
def state() -> GameState:
    return GameState(SpyEffectControls(), SceneControls())


# ---------------------------------------------------------------------------
# next_in_cycle
# ---------------------------------------------------------------------------


def test_next_in_cycle_advances_through_all_five_modes_and_wraps():
    sequence = [MODE_RGB]
    current = MODE_RGB
    for _ in range(5):
        current = next_in_cycle(MODE_ORDER, current)
        sequence.append(current)

    assert sequence == [
        MODE_RGB,
        MODE_ACCELEROMETER,
        MODE_IR,
        MODE_RADIO,
        MODE_SFX,
        MODE_RGB,
    ]


# ---------------------------------------------------------------------------
# Flash
# ---------------------------------------------------------------------------


def test_new_flash_has_no_receipt():
    flash = Flash()

    assert flash.receipt is None


def test_new_flash_is_not_expired():
    flash = Flash()

    assert not flash.expired(now=100.0, duration=0.5)


def test_flash_not_expired_before_duration_elapsed():
    flash = Flash()
    flash.restart(now=10.0, receipt=EffectReceipt(1))

    assert not flash.expired(now=10.0 + 0.49, duration=0.5)


def test_flash_expired_after_duration_elapsed():
    flash = Flash()
    flash.restart(now=10.0, receipt=EffectReceipt(1))

    assert flash.expired(now=10.0 + 0.51, duration=0.5)


def test_restart_sets_receipt_and_start_time():
    flash = Flash()
    receipt = EffectReceipt(7)

    flash.restart(now=5.0, receipt=receipt)

    assert flash.receipt is receipt
    assert flash.start_time == 5.0

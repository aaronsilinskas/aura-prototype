"""Tests for the hw_test rules/helpers subpackage."""

from __future__ import annotations

from engine.state import EffectReceipt
from packs.scenes.hardware_test.rules.helpers.flash import Flash


def test_new_flash_has_no_receipt():
    flash = Flash()

    assert flash.receipt is None


def test_new_flash_is_not_expired():
    flash = Flash()

    assert not flash.expired(now=100.0, duration=0.5)


def test_restart_sets_receipt_and_start_time():
    flash = Flash()
    receipt = EffectReceipt(7)

    flash.restart(now=5.0, receipt=receipt)

    assert flash.receipt is receipt
    assert flash.start_time == 5.0

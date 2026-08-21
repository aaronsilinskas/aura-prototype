"""Tests for ``TransmitterConfig`` — resolution from seeded state, and the
``transmitter_config`` get-or-create accessor."""

from __future__ import annotations

import pytest

from engine.engine import GameEngine
from engine.state import SceneControls
from engine.tests.helpers import SpyEffectControls
from packs.scenes.ir_range_transmitter.rules.helpers.transmitter_config import (
    TransmitterConfig,
    transmitter_config,
)


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
# from_state — defaults and overrides
# ---------------------------------------------------------------------------


def test_from_state_applies_defaults_when_unseeded():
    state = _make_state()

    config = TransmitterConfig.from_state(state)

    assert config.send_rate_hz == pytest.approx(5.0)
    assert config.payload_size == 4


def test_from_state_reads_seeded_overrides():
    state = _make_state(initial_data={"irtx_send_rate_hz": 10.0, "irtx_payload_size": 8})

    config = TransmitterConfig.from_state(state)

    assert config.send_rate_hz == pytest.approx(10.0)
    assert config.payload_size == 8


# ---------------------------------------------------------------------------
# Derived values
# ---------------------------------------------------------------------------


def test_send_period_seconds_is_the_reciprocal_of_send_rate():
    config = TransmitterConfig(send_rate_hz=10.0, payload_size=4)

    assert config.send_period_seconds == pytest.approx(0.1)


def test_payload_padding_carries_a_fixed_non_zero_marker_in_every_padding_byte():
    config = TransmitterConfig(send_rate_hz=5.0, payload_size=4)

    assert config.payload_padding == bytes([0xA1, 0xA2, 0xA3])


# ---------------------------------------------------------------------------
# transmitter_config — get-or-create accessor
# ---------------------------------------------------------------------------


def test_transmitter_config_reflects_seeded_overrides_on_first_build():
    state = _make_state(initial_data={"irtx_payload_size": 8})

    assert transmitter_config(state).payload_size == 8


def test_transmitter_config_caches_the_same_instance_across_calls():
    state = _make_state(initial_data={"irtx_send_rate_hz": 10.0})

    first = transmitter_config(state)
    second = transmitter_config(state)

    assert first is second


def test_transmitter_config_does_not_reflect_state_changes_after_first_build():
    """The config is built once and cached — later state mutations are not re-read."""
    state = _make_state(initial_data={"irtx_send_rate_hz": 10.0})

    config = transmitter_config(state)
    assert config.send_rate_hz == pytest.approx(10.0)

    state.set("irtx_send_rate_hz", 1.0)

    assert transmitter_config(state).send_rate_hz == pytest.approx(10.0)

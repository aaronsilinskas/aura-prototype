"""The IR range transmitter's sends, played on a simulated device.

Every assertion reads ``ir_sent``: what reached the wire, when, and on which
emitter. A test that depends on a tunable pins it with ``scene_data`` rather
than restating the scene's default.
"""

from __future__ import annotations

from itertools import pairwise

import pytest

from app.simulation import TICK, SimulatedDevice
from engine.network import LINE

FIVE_HZ = {"irtx_send_rate_hz": 5.0}
"""One send every 0.2 s: twelve ticks apart."""

EVERY_TICK = {"irtx_send_rate_hz": 1000.0}
"""A rate far above the tick rate, so the transmitter sends on every tick."""


def sequences(transmitter: SimulatedDevice) -> list[int]:
    return [s.payload[0] for s in transmitter.ir_sent]


def test_sends_start_on_the_first_tick_without_any_input(simulation):
    transmitter = simulation.add_device("tx", scene="ir_range_transmitter", scene_data=FIVE_HZ)

    simulation.advance(TICK)

    assert [s.at for s in transmitter.ir_sent] == [pytest.approx(TICK)]


def test_every_send_goes_out_on_the_line_emitter(simulation):
    transmitter = simulation.add_device("tx", scene="ir_range_transmitter", scene_data=FIVE_HZ)

    simulation.advance(1.0)

    assert {s.emitter for s in transmitter.ir_sent} == {LINE}


def test_sends_go_out_at_the_configured_rate(simulation):
    transmitter = simulation.add_device("tx", scene="ir_range_transmitter", scene_data=FIVE_HZ)

    simulation.advance(2.0)

    times = [s.at for s in transmitter.ir_sent]
    gaps = [later - earlier for earlier, later in pairwise(times)]
    assert len(times) == 10
    assert all(gap == pytest.approx(0.2, abs=TICK) for gap in gaps)


def test_successive_sends_carry_incrementing_sequence_numbers(simulation):
    transmitter = simulation.add_device("tx", scene="ir_range_transmitter", scene_data=FIVE_HZ)

    simulation.advance(0.5)

    assert sequences(transmitter) == [0, 1, 2]


def test_the_sequence_number_wraps_from_255_back_to_zero(simulation):
    transmitter = simulation.add_device("tx", scene="ir_range_transmitter", scene_data=EVERY_TICK)

    simulation.advance(257 * TICK)

    assert sequences(transmitter)[254:] == [254, 255, 0]


@pytest.mark.parametrize("size", [1, 4, 8])
def test_each_send_carries_the_configured_payload_size(simulation, size):
    transmitter = simulation.add_device(
        "tx", scene="ir_range_transmitter", scene_data={**FIVE_HZ, "irtx_payload_size": size}
    )

    simulation.advance(0.5)

    assert {len(s.payload) for s in transmitter.ir_sent} == {size}


def test_bytes_after_the_sequence_number_carry_the_fixed_padding_marker(simulation):
    transmitter = simulation.add_device(
        "tx", scene="ir_range_transmitter", scene_data={**FIVE_HZ, "irtx_payload_size": 4}
    )

    simulation.advance(TICK)

    assert transmitter.ir_sent[0].payload[1:] == bytes([0xA1, 0xA2, 0xA3])

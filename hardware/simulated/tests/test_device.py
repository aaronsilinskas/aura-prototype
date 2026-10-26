"""The Simulated device takes its hardware shape from a ``DeviceConfig``."""

from __future__ import annotations

import pytest

from engine.input import ButtonData
from engine.network import CONE, LINE
from engine.state import Scope
from hardware.shared.device_config import DeviceConfig, parse_device_config
from hardware.shared.ir_codecs.tag import TagInfraredDecoder, TagInfraredEncoder
from hardware.shared.ir_transceiver import InfraredTransceiver
from hardware.simulated.device import IrSent, SimulatedHardware


def _config(**sections: object) -> DeviceConfig:
    return parse_device_config(
        {
            "pixels": [
                {
                    "type": "neopixel",
                    "pin": "P0",
                    "count": 4,
                    "scope_pixels": {"personal": [0, 4]},
                },
                {
                    "type": "neopixel",
                    "pin": "P1",
                    "count": 7,
                    "scope_pixels": {"directional": [0, 7]},
                },
            ],
            **sections,
        }
    )


def _read_buttons(sim_hw: SimulatedHardware) -> ButtonData:
    """Apply due pin changes, then read the buttons once a debounce interval has passed."""
    out = ButtonData(states={})
    sim_hw.settle_pins()
    sim_hw.hw.buttons.update(0.5, out)
    return out


def test_each_scope_strip_is_as_long_as_its_configured_segment():
    sim_hw = SimulatedHardware(now=lambda: 0.0, config=_config())

    assert sim_hw.strip(Scope.PERSONAL).size == 4
    assert sim_hw.strip(Scope.DIRECTIONAL).size == 7


def test_a_scope_strip_starts_dark():
    sim_hw = SimulatedHardware(now=lambda: 0.0, config=_config())

    assert sim_hw.strip(Scope.PERSONAL).dark


def test_buttons_are_labelled_a_onward_one_per_configured_pin():
    sim_hw = SimulatedHardware(now=lambda: 0.0, config=_config(buttons=["GP2", "GP3", "GP4"]))

    for label in ("A", "B", "C"):
        sim_hw.hold(label)
    out = _read_buttons(sim_hw)

    assert sorted(label for label, _ in out.items()) == ["A", "B", "C"]
    assert all(out.is_pressed(label) for label in ("A", "B", "C"))


def test_a_button_the_config_does_not_declare_cannot_be_held():
    sim_hw = SimulatedHardware(now=lambda: 0.0, config=_config(buttons=["GP2"]))

    with pytest.raises(KeyError):
        sim_hw.hold("B")


def test_a_matrix_pixel_entry_is_rejected():
    config = parse_device_config(
        {"pixels": [{"type": "matrix", "cols": 13, "scope_rows": {"personal": [0, 1]}}]}
    )

    with pytest.raises(ValueError, match="matrix"):
        SimulatedHardware(now=lambda: 0.0, config=config)


# ---------------------------------------------------------------------------
# IR
# ---------------------------------------------------------------------------

LINE_ONLY_IR = {"rx": "GP5", "line": "GP6"}


def _ir(sim_hw: SimulatedHardware) -> InfraredTransceiver:
    assert sim_hw.hw.ir is not None
    return sim_hw.hw.ir


def test_sending_on_an_emitter_the_config_does_not_wire_raises():
    sim_hw = SimulatedHardware(now=lambda: 0.0, config=_config(ir=LINE_ONLY_IR))

    with pytest.raises(ValueError, match="cone"):
        sim_hw.hw.network_controls.send_ir(b"\x01", CONE)


def test_a_device_without_an_ir_section_cannot_send():
    sim_hw = SimulatedHardware(now=lambda: 0.0, config=_config())

    with pytest.raises(ValueError, match="line"):
        sim_hw.hw.network_controls.send_ir(b"\x01", LINE)


def test_ir_sent_records_the_payload_the_wire_carried_per_emitter():
    sim_hw = SimulatedHardware(now=lambda: 2.5, config=_config(ir=LINE_ONLY_IR))

    sim_hw.hw.network_controls.send_ir(b"\x12\x34", LINE)

    assert sim_hw.ir_sent == [IrSent(at=2.5, emitter=LINE, payload=b"\x12\x34")]


def test_ir_sent_holds_only_what_the_installed_codec_put_on_the_wire():
    sim_hw = SimulatedHardware(now=lambda: 0.0, config=_config(ir=LINE_ONLY_IR))
    sim_hw.apply_ir_codec(TagInfraredEncoder(), TagInfraredDecoder())

    # The Tag wire-frame carries 7 bits of the first byte only.
    sim_hw.hw.network_controls.send_ir(b"\xff\x01", LINE)

    assert [s.payload for s in sim_hw.ir_sent] == [b"\x7f"]


@pytest.mark.parametrize("rx", ["GP5", ["GP5", "GP7", "GP8"]], ids=["one-rx", "three-rx"])
def test_a_received_payload_decodes_on_the_next_transceiver_update(rx):
    sim_hw = SimulatedHardware(now=lambda: 0.0, config=_config(ir={"rx": rx}))

    sim_hw.receive_ir(b"\x12\x34")
    _ir(sim_hw).update()

    assert _ir(sim_hw).received == b"\x12\x34"


def test_a_received_payload_reports_full_signal_strength():
    sim_hw = SimulatedHardware(now=lambda: 0.0, config=_config(ir=LINE_ONLY_IR))

    sim_hw.receive_ir(b"\x12")
    _ir(sim_hw).update()

    assert _ir(sim_hw).last_signal_strength == 1.0


def test_a_received_payload_travels_the_installed_codecs_wire():
    sim_hw = SimulatedHardware(now=lambda: 0.0, config=_config(ir=LINE_ONLY_IR))
    sim_hw.apply_ir_codec(TagInfraredEncoder(), TagInfraredDecoder())

    sim_hw.receive_ir(b"\xff\x01")
    _ir(sim_hw).update()

    assert _ir(sim_hw).received == b"\x7f"


def test_payloads_received_together_decode_one_per_update():
    sim_hw = SimulatedHardware(now=lambda: 0.0, config=_config(ir=LINE_ONLY_IR))

    sim_hw.receive_ir(b"\x01")
    sim_hw.receive_ir(b"\x02")
    received = []
    for _ in range(3):
        _ir(sim_hw).update()
        received.append(_ir(sim_hw).received)

    assert received == [b"\x01", b"\x02", None]


def test_a_device_never_decodes_its_own_send():
    sim_hw = SimulatedHardware(now=lambda: 0.0, config=_config(ir=LINE_ONLY_IR))

    sim_hw.hw.network_controls.send_ir(b"\x01", LINE)
    received = []
    for _ in range(2):
        _ir(sim_hw).update()
        received.append(_ir(sim_hw).received)

    assert received == [None, None]


def test_a_payload_landing_with_the_devices_own_send_is_dropped_with_it():
    sim_hw = SimulatedHardware(now=lambda: 0.0, config=_config(ir=LINE_ONLY_IR))

    sim_hw.hw.network_controls.send_ir(b"\x01", LINE)
    sim_hw.receive_ir(b"\x02")
    _ir(sim_hw).update()

    assert _ir(sim_hw).received is None


# ---------------------------------------------------------------------------
# Accelerometer
# ---------------------------------------------------------------------------

ACCELEROMETER = {"enabled": True}


def _acceleration(sim_hw: SimulatedHardware) -> tuple[float, float, float]:
    accelerometer = sim_hw.hw.accelerometer
    assert accelerometer is not None
    return accelerometer.acceleration  # type: ignore[attr-defined]


def test_a_device_boots_still_with_gravity_on_z():
    sim_hw = SimulatedHardware(now=lambda: 0.0, config=_config(accelerometer=ACCELEROMETER))

    assert _acceleration(sim_hw) == (0.0, 0.0, 9.81)


@pytest.mark.parametrize("sections", [{}, {"accelerometer": {"enabled": False}}])
def test_a_device_has_an_accelerometer_only_when_the_config_enables_one(sections):
    sim_hw = SimulatedHardware(now=lambda: 0.0, config=_config(**sections))

    assert sim_hw.hw.accelerometer is None


def test_accelerate_holds_its_reading_over_time():
    clock = [0.0]
    sim_hw = SimulatedHardware(now=lambda: clock[0], config=_config(accelerometer=ACCELEROMETER))

    sim_hw.accelerate(3.0, -2.0, 9.0)
    first = _acceleration(sim_hw)
    clock[0] = 5.0

    assert first == (3.0, -2.0, 9.0)
    assert _acceleration(sim_hw) == (3.0, -2.0, 9.0)


def _readings_over(
    sim_hw: SimulatedHardware, clock: list[float], seconds: float
) -> list[tuple[float, float, float]]:
    """One reading per 60 Hz tick for *seconds*, advancing *clock* as it goes."""
    readings = []
    for _ in range(round(seconds * 60)):
        clock[0] += 1 / 60
        readings.append(_acceleration(sim_hw))
    return readings


def _distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return sum((p - q) ** 2 for p, q in zip(a, b, strict=True)) ** 0.5


def _strays(readings: list[tuple[float, float, float]], rest: tuple[float, float, float]) -> bool:
    """Whether every quarter second of *readings* swings more than 3 m/s² off *rest*."""
    windows = [readings[i : i + 15] for i in range(0, len(readings), 15)]
    return all(max(_distance(r, rest) for r in window) > 3.0 for window in windows)


def test_move_keeps_swaying_well_away_from_the_held_reading():
    clock = [0.0]
    sim_hw = SimulatedHardware(now=lambda: clock[0], config=_config(accelerometer=ACCELEROMETER))
    sim_hw.accelerate(1.0, 2.0, 9.0)

    sim_hw.move()

    assert _strays(_readings_over(sim_hw, clock, 2.0), rest=(1.0, 2.0, 9.0))


def test_hold_still_returns_to_rest_and_stops_moving():
    clock = [0.0]
    sim_hw = SimulatedHardware(now=lambda: clock[0], config=_config(accelerometer=ACCELEROMETER))
    sim_hw.accelerate(3.0, -2.0, 9.0)
    sim_hw.move()
    clock[0] = 0.3

    sim_hw.hold_still()

    assert set(_readings_over(sim_hw, clock, 1.0)) == {(0.0, 0.0, 9.81)}


def test_a_device_without_an_accelerometer_cannot_be_moved():
    sim_hw = SimulatedHardware(now=lambda: 0.0, config=_config())

    with pytest.raises(ValueError, match="accelerometer"):
        sim_hw.move()

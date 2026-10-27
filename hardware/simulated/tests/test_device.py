"""The Simulated device takes its hardware shape from a ``DeviceConfig``."""

from __future__ import annotations

import pytest

from engine.input import ButtonData
from engine.network import CONE, LINE
from engine.state import Scope
from hardware.shared.device_config import DeviceConfig, parse_device_config
from hardware.shared.ir_codecs.tag import TagInfraredDecoder, TagInfraredEncoder
from hardware.shared.ir_transceiver import InfraredTransceiver
from hardware.simulated.device import IrSent, SimulatedHardware, Strip


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


RED = 0xFF0000
AMBER = 0xFFBF00


@pytest.mark.parametrize(
    ("pixels", "color"),
    [
        ([0xFF0000, 0x800000, 0x010000], RED),
        ([0x000000, 0x400000, 0x000000], RED),
        ([0xFFBF00, 0x806000, 0x403000], AMBER),
    ],
    ids=["dimmed", "partly-dark", "mixed-color"],
)
def test_a_strip_lit_only_in_dimmed_copies_of_a_color_shows_shades_of_it(pixels, color):
    assert Strip(pixels).shades_of(color)


@pytest.mark.parametrize(
    ("pixels", "color"),
    [
        ([0xFF0000, 0xFF0100], RED),
        ([0xFF0000, 0x00FF00], RED),
        ([0x7F7F00], AMBER),
        ([0xFF0000], 0x800000),
    ],
    ids=["one-pixel-off-hue", "another-color", "wrong-mix", "brighter-than-the-color"],
)
def test_a_strip_with_any_lit_pixel_off_the_color_does_not_show_shades_of_it(pixels, color):
    assert not Strip(pixels).shades_of(color)


def test_a_dark_strip_counts_as_shades_of_any_color():
    assert Strip([0, 0, 0]).shades_of(0x00FF00)


def test_buttons_are_labelled_a_onward_one_per_configured_pin():
    sim_hw = SimulatedHardware(now=lambda: 0.0, config=_config(buttons=["GP2", "GP3", "GP4"]))

    for label in ("A", "B", "C"):
        sim_hw.hold(label)
    out = _read_buttons(sim_hw)

    assert sorted(label for label, _ in out.items()) == ["A", "B", "C"]
    assert all(out.is_pressed(label) for label in ("A", "B", "C"))


def test_buttons_held_together_press_at_once_even_behind_a_recent_release():
    clock = [0.0]
    sim_hw = SimulatedHardware(now=lambda: clock[0], config=_config(buttons=["GP2", "GP3"]))
    sim_hw.hold("A")
    sim_hw.release("A")

    sim_hw.hold("A", "B")
    _read_buttons(sim_hw)  # A down
    clock[0] = 0.15
    b_before_a_settles = _read_buttons(sim_hw).is_down("B")  # A's release lands, still settling
    clock[0] = 0.2
    out = _read_buttons(sim_hw)

    assert (b_before_a_settles, out.is_pressed("A"), out.is_pressed("B")) == (False, True, True)


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
    _ir(sim_hw).apply_codec(TagInfraredEncoder(), TagInfraredDecoder())

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
    _ir(sim_hw).apply_codec(TagInfraredEncoder(), TagInfraredDecoder())

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

Reading = tuple[float, float, float]
"""An ``(x, y, z)`` acceleration in m/s², as the accelerometer reports it."""

TICK = 1 / 60
"""The 60 Hz scene tick a reading is taken on."""


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _with_accelerometer(clock: _Clock) -> SimulatedHardware:
    return SimulatedHardware(now=clock, config=_config(accelerometer={"enabled": True}))


def _acceleration(sim_hw: SimulatedHardware) -> Reading:
    accelerometer = sim_hw.hw.accelerometer
    assert accelerometer is not None
    # DeviceHardware types every sensor as a bare ``object``, as the board's driver is untyped.
    return accelerometer.acceleration  # type: ignore[attr-defined]


def _readings_over(sim_hw: SimulatedHardware, clock: _Clock, seconds: float) -> list[Reading]:
    """One reading per tick for *seconds*, advancing *clock* as it goes."""
    readings = []
    for _ in range(round(seconds / TICK)):
        clock.now += TICK
        readings.append(_acceleration(sim_hw))
    return readings


def _distance(a: Reading, b: Reading) -> float:
    return sum((p - q) ** 2 for p, q in zip(a, b, strict=True)) ** 0.5


def _keeps_straying(readings: list[Reading], rest: Reading) -> bool:
    """Whether every quarter second of *readings* swings more than 3 m/s² off *rest*."""
    window = round(0.25 / TICK)
    windows = [readings[i : i + window] for i in range(0, len(readings), window)]
    return all(max(_distance(r, rest) for r in w) > 3.0 for w in windows)


def test_a_device_boots_still_with_gravity_on_z():
    sim_hw = _with_accelerometer(_Clock())

    assert _acceleration(sim_hw) == (0.0, 0.0, 9.81)


@pytest.mark.parametrize("sections", [{}, {"accelerometer": {"enabled": False}}])
def test_a_device_has_an_accelerometer_only_when_the_config_enables_one(sections):
    sim_hw = SimulatedHardware(now=lambda: 0.0, config=_config(**sections))

    assert sim_hw.hw.accelerometer is None


def test_accelerate_holds_its_reading_over_time():
    clock = _Clock()
    sim_hw = _with_accelerometer(clock)

    sim_hw.accelerate(3.0, -2.0, 9.0)

    assert set(_readings_over(sim_hw, clock, 1.0)) == {(3.0, -2.0, 9.0)}


def test_move_keeps_swaying_well_away_from_the_held_reading():
    clock = _Clock()
    sim_hw = _with_accelerometer(clock)
    sim_hw.accelerate(1.0, 2.0, 9.0)

    sim_hw.move()

    assert _keeps_straying(_readings_over(sim_hw, clock, 2.0), rest=(1.0, 2.0, 9.0))


def test_hold_still_returns_to_rest_and_stops_moving():
    clock = _Clock()
    sim_hw = _with_accelerometer(clock)
    sim_hw.accelerate(3.0, -2.0, 9.0)
    sim_hw.move()
    clock.now = 0.3

    sim_hw.hold_still()

    assert set(_readings_over(sim_hw, clock, 1.0)) == {(0.0, 0.0, 9.81)}


@pytest.mark.parametrize(
    "drive",
    [lambda hw: hw.accelerate(0.0, 0.0, 0.0), lambda hw: hw.move(), lambda hw: hw.hold_still()],
    ids=["accelerate", "move", "hold_still"],
)
def test_a_device_without_an_accelerometer_cannot_be_driven(drive):
    sim_hw = SimulatedHardware(now=lambda: 0.0, config=_config())

    with pytest.raises(ValueError, match="accelerometer"):
        drive(sim_hw)


_RADIO = {"radio": {"cs": "P2", "reset": "P3", "frequency": 915.0, "node": 9}}


def test_a_radio_send_is_handed_to_the_radio_sink():
    sent: list[bytes] = []
    sim_hw = SimulatedHardware(now=lambda: 0.0, config=_config(**_RADIO), radio_sink=sent.append)

    sim_hw.hw.network_controls.send_radio(b"ping")

    assert sent == [b"ping"]


def test_a_landed_radio_packet_is_read_with_its_sender():
    sim_hw = SimulatedHardware(now=lambda: 0.0, config=_config(**_RADIO))
    radio = sim_hw.hw.radio
    assert radio is not None

    sim_hw.land_radio(b"ping", sender=4)
    radio.update()

    assert radio.received == b"ping"
    assert radio.last_sender == 4


def test_a_reset_loses_radio_packets_not_yet_read():
    sim_hw = SimulatedHardware(now=lambda: 0.0, config=_config(**_RADIO))
    sim_hw.land_radio(b"ping", sender=4)

    sim_hw.power_on()
    radio = sim_hw.hw.radio
    assert radio is not None
    radio.update()

    assert radio.received is None


def test_with_no_radio_declared_the_device_has_none():
    sim_hw = SimulatedHardware(now=lambda: 0.0, config=_config())

    assert sim_hw.hw.radio is None


def test_with_no_radio_declared_a_packet_cannot_land():
    sim_hw = SimulatedHardware(now=lambda: 0.0, config=_config())

    with pytest.raises(ValueError, match="no radio"):
        sim_hw.land_radio(b"ping", sender=4)


_MAGNETOMETER = {"magnetometer": {"enabled": True}}


def test_a_magnetometer_switches_on_reading_a_zero_field():
    sim_hw = SimulatedHardware(now=lambda: 0.0, config=_config(**_MAGNETOMETER))

    assert sim_hw.hw.magnetometer.magnetic == (0.0, 0.0, 0.0)  # type: ignore[attr-defined]


@pytest.mark.parametrize("sections", [{}, {"magnetometer": {"enabled": False}}])
def test_a_device_has_a_magnetometer_only_when_the_config_enables_one(sections):
    sim_hw = SimulatedHardware(now=lambda: 0.0, config=_config(**sections))

    assert sim_hw.hw.magnetometer is None


def test_without_a_magnetometer_a_field_cannot_be_set():
    sim_hw = SimulatedHardware(now=lambda: 0.0, config=_config())

    with pytest.raises(ValueError, match="no magnetometer"):
        sim_hw.magnetize(1.0, 2.0, 3.0)

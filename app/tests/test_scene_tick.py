"""Behaviour-driven tests for the tick ``build_scene_boot`` hands back, the
per-tick body the device and the Simulated device share: each test boots the
probe scene and checks what its rule hears."""

from engine.input import AccelerationData, ButtonData, InputEvents, MagneticData
from engine.log import Logger
from engine.network import NetworkEvents
from engine.tests.helpers import FrozenTimer, SpyNetworkControls
from hardware.shared.debounced_buttons import DebouncedButtons
from hardware.shared.device_hardware import DeviceHardware
from hardware.shared.polled_part import PolledPart
from hardware.shared.polled_sensor import PolledSensor


def _hw(
    probe,
    buttons=None,
    accelerometer=None,
    magnetometer=None,
    ir=None,
    radio=None,
    other_polled=(),
):
    """Return a DeviceHardware of CPython-safe fakes, carrying the probe's card.

    Its ``polled`` lists every part given, as the Device assembly lists what it
    built, followed by ``other_polled``.
    """
    buttons = buttons if buttons is not None else DebouncedButtons([])
    built = (buttons, accelerometer, magnetometer, radio, ir)
    return DeviceHardware(
        outputs=[],
        buttons=buttons,
        accelerometer=accelerometer,
        magnetometer=magnetometer,
        network_controls=SpyNetworkControls(),
        ir=ir,
        radio=radio,
        storage=probe.storage,
        capabilities=frozenset(),
        polled=tuple(part for part in built if part is not None) + tuple(other_polled),
    )


def test_each_tick_delivers_one_sensors_event_carrying_the_debounced_button_states(probe):
    tick = probe.boot(_hw(probe, buttons=DebouncedButtons([("A", lambda: True)]))).tick

    tick()

    [sensors] = probe.events(InputEvents.Sensors)
    assert sensors.buttons.get("A") == ButtonData.UP


def test_ticks_reuse_one_sensors_event_and_button_buffer_instead_of_allocating(probe):
    tick = probe.boot(_hw(probe, buttons=DebouncedButtons([("A", lambda: True)]))).tick

    tick()
    tick()
    tick()

    first, *rest = probe.events(InputEvents.Sensors)
    assert len(rest) == 2
    assert all(event is first for event in rest)
    assert all(event.buttons is first.buttons for event in rest)


def test_the_sensors_event_carries_the_latest_accelerometer_and_magnetometer_readings(probe):
    hw = _hw(
        probe,
        accelerometer=PolledSensor(
            lambda: (1.0, 2.0, 3.0), AccelerationData(0.0, 0.0, 0.0), "accelerometer", Logger.SILENT
        ),
        magnetometer=PolledSensor(
            lambda: (4.0, 5.0, 6.0), MagneticData(0.0, 0.0, 0.0), "magnetometer", Logger.SILENT
        ),
    )
    tick = probe.boot(hw).tick

    tick()

    [event] = probe.events(InputEvents.Sensors)
    assert event.acceleration is not None
    assert event.magnetic is not None
    assert (event.acceleration.x, event.acceleration.y, event.acceleration.z) == (1.0, 2.0, 3.0)
    assert (event.magnetic.x, event.magnetic.y, event.magnetic.z) == (4.0, 5.0, 6.0)


def test_a_device_without_an_accelerometer_or_magnetometer_reports_none_for_them(probe):
    tick = probe.boot(_hw(probe)).tick

    tick()

    [event] = probe.events(InputEvents.Sensors)
    assert event.acceleration is None
    assert event.magnetic is None


class _FakeIr:
    """InfraredTransceiver stand-in: counts pumps and exposes one scripted packet."""

    def __init__(self, received: bytes | None = None, telemetry: str | None = None) -> None:
        self.received = received
        self.last_signal_strength = 87
        self.last_error_margin = 3
        self.telemetry = telemetry
        self.update_count = 0

    def apply_codec(self, encoder_class, decoder_factory) -> None:
        pass

    def update(self, elapsed: float) -> None:
        self.update_count += 1

    def telemetry_line(self) -> str | None:
        return self.telemetry


class _FakeRadio:
    """RadioTransceiver stand-in: counts polls and exposes one scripted packet."""

    def __init__(self, received: bytes | None = None, last_sender: int = 0) -> None:
        self.received = received
        self.last_sender = last_sender
        self.update_count = 0

    def update(self, elapsed: float) -> None:
        self.update_count += 1


def test_a_received_ir_packet_reaches_the_rules_as_ir_received_in_the_same_tick(probe):
    tick = probe.boot(_hw(probe, ir=_FakeIr(received=b"\x01\x02"))).tick

    tick()

    [event] = probe.events(NetworkEvents.IRReceived)
    assert event.data == b"\x01\x02"
    assert event.signal_strength == 87
    assert event.error_margin == 3


def test_a_received_radio_packet_reaches_the_rules_as_radio_received_in_the_same_tick(probe):
    tick = probe.boot(_hw(probe, radio=_FakeRadio(received=b"\x09", last_sender=42))).tick

    tick()

    [event] = probe.events(NetworkEvents.RadioReceived)
    assert event.data == b"\x09"
    assert event.sender == "42"


class _CountingPart(PolledPart):
    """A Polled part the tick has never heard of: counts its updates."""

    def __init__(self) -> None:
        self.update_count = 0

    def update(self, elapsed: float) -> None:
        self.update_count += 1


def test_every_polled_part_is_updated_every_tick_even_when_no_event_results(probe):
    ir = _FakeIr()
    radio = _FakeRadio()
    part = _CountingPart()
    tick = probe.boot(_hw(probe, ir=ir, radio=radio, other_polled=(part,))).tick

    tick()
    tick()

    assert (ir.update_count, radio.update_count, part.update_count) == (2, 2, 2)
    assert probe.events(NetworkEvents.IRReceived) == []
    assert probe.events(NetworkEvents.RadioReceived) == []


def test_the_ir_telemetry_line_prints_at_most_once_per_second_of_scene_time(probe, capsys):
    timer = FrozenTimer()
    tick = probe.boot(_hw(probe, ir=_FakeIr(telemetry="ir: rx=3")), timer=timer).tick

    for _ in range(5):
        timer.total += 0.3
        tick()

    # totals 0.3, 0.6, 0.9, 1.2 (prints), 1.5 -> one line inside the first 1.5 s
    assert capsys.readouterr().out == "ir: rx=3\n"


def test_no_telemetry_prints_when_the_ir_reports_no_change(probe, capsys):
    timer = FrozenTimer()
    tick = probe.boot(_hw(probe, ir=_FakeIr(telemetry=None)), timer=timer).tick

    timer.total = 5.0
    tick()

    assert capsys.readouterr().out == ""

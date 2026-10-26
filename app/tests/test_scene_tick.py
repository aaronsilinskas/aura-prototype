"""Behaviour-driven tests for build_scene_tick, the per-tick loop shared by
the device and the Simulated device (issue #958)."""

from app.scene_composition import (
    SceneRuntime,
    build_scene_runtime,
    build_scene_tick,
    scan_boot_scene_registry,
)
from engine.events import Event
from engine.input import ButtonData, InputEvents
from engine.network import LINE, NetworkEvents
from engine.tests.helpers import SpyNetworkControls
from engine.timer import Timer
from hardware.shared.debounced_buttons import DebouncedButtons
from hardware.shared.device_hardware import DeviceHardware


def _hw(buttons=None, accelerometer=None, magnetometer=None, ir=None, radio=None):
    """Return a DeviceHardware built entirely from CPython-safe fakes."""
    return DeviceHardware(
        outputs=[],
        buttons=buttons if buttons is not None else DebouncedButtons([]),
        accelerometer=accelerometer,
        magnetometer=magnetometer,
        network_controls="fake-network-controls",
        ir=ir,
        radio=radio,
        storage=None,
        audio_registry=None,
    )


class _RecordingState:
    """Stands in for the active scene's GameState: keeps every queued event."""

    def __init__(self) -> None:
        self.queued: list[Event] = []

    def queue_event(self, event: Event) -> None:
        self.queued.append(event)


class _RecordingManager:
    """Stands in for SceneManager: an active state, and a timer advanced on update
    the way GameEngine.update advances it."""

    def __init__(self, timer: Timer, active: bool = True) -> None:
        self.active_state = _RecordingState() if active else None
        self._timer = timer
        self.update_count = 0

    def update(self) -> None:
        self.update_count += 1
        self._timer.update()


class _RecordingEffectManager:
    def __init__(self) -> None:
        self.updated_with: list[Timer] = []

    def update(self, timer: Timer) -> None:
        self.updated_with.append(timer)


def _runtime(hw: DeviceHardware, active: bool = True) -> SceneRuntime:
    timer = Timer()
    return SceneRuntime(
        manager=_RecordingManager(timer, active=active),
        effect_manager=_RecordingEffectManager(),
        timer=timer,
        ir=hw.ir,
        radio=hw.radio,
    )


def _queued(runtime: SceneRuntime, event_type: type[Event]) -> list[Event]:
    return [e for e in runtime.manager.active_state.queued if isinstance(e, event_type)]


def _sensors(runtime: SceneRuntime) -> list[InputEvents.Sensors]:
    return _queued(runtime, InputEvents.Sensors)


def test_each_tick_queues_one_sensors_event_carrying_the_debounced_button_states():
    hw = _hw(buttons=DebouncedButtons([("A", lambda: True)]))
    runtime = _runtime(hw)
    tick = build_scene_tick(hw, runtime)

    tick()

    sensors = _sensors(runtime)
    assert len(sensors) == 1
    assert sensors[0].buttons.get("A") == ButtonData.UP


def test_every_tick_reuses_the_same_sensors_event_and_button_buffer():
    hw = _hw(buttons=DebouncedButtons([("A", lambda: True)]))
    runtime = _runtime(hw)
    tick = build_scene_tick(hw, runtime)

    tick()
    tick()
    tick()

    first, *rest = _sensors(runtime)
    assert all(event is first for event in rest)
    assert all(event.buttons is first.buttons for event in rest)


class _Sensor:
    """Accelerometer/magnetometer stand-in: replays scripted readings, where an
    Exception entry makes that read raise."""

    def __init__(self, *readings) -> None:
        self._readings = list(readings)

    def _next(self):
        reading = self._readings.pop(0)
        if isinstance(reading, Exception):
            raise reading
        return reading

    acceleration = property(_next)
    magnetic = property(_next)


def test_the_sensors_event_carries_the_latest_accelerometer_and_magnetometer_readings():
    hw = _hw(accelerometer=_Sensor((1.0, 2.0, 3.0)), magnetometer=_Sensor((4.0, 5.0, 6.0)))
    runtime = _runtime(hw)
    tick = build_scene_tick(hw, runtime)

    tick()

    event = _sensors(runtime)[0]
    assert (event.acceleration.x, event.acceleration.y, event.acceleration.z) == (1.0, 2.0, 3.0)
    assert (event.magnetic.x, event.magnetic.y, event.magnetic.z) == (4.0, 5.0, 6.0)


def test_a_failed_sensor_read_keeps_the_last_good_reading():
    hw = _hw(
        accelerometer=_Sensor((1.0, 2.0, 3.0), OSError("i2c")),
        magnetometer=_Sensor((4.0, 5.0, 6.0), OSError("i2c")),
    )
    runtime = _runtime(hw)
    tick = build_scene_tick(hw, runtime)

    tick()
    tick()

    event = _sensors(runtime)[-1]
    assert (event.acceleration.x, event.acceleration.y, event.acceleration.z) == (1.0, 2.0, 3.0)
    assert (event.magnetic.x, event.magnetic.y, event.magnetic.z) == (4.0, 5.0, 6.0)


def test_a_device_without_an_accelerometer_or_magnetometer_reports_none_for_them():
    hw = _hw()
    runtime = _runtime(hw)
    tick = build_scene_tick(hw, runtime)

    tick()

    event = _sensors(runtime)[0]
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
        self.telemetry_calls = 0

    def update(self) -> None:
        self.update_count += 1

    def telemetry_line(self) -> str | None:
        self.telemetry_calls += 1
        return self.telemetry


class _FakeRadio:
    """RadioTransceiver stand-in: counts polls and exposes one scripted packet."""

    def __init__(self, received: bytes | None = None, last_sender: int = 0) -> None:
        self.received = received
        self.last_sender = last_sender
        self.update_count = 0

    def update(self) -> None:
        self.update_count += 1


def test_a_received_ir_packet_is_queued_as_ir_received_with_its_telemetry():
    hw = _hw(ir=_FakeIr(received=b"\x01\x02"))
    runtime = _runtime(hw)
    tick = build_scene_tick(hw, runtime)

    tick()

    [event] = _queued(runtime, NetworkEvents.IRReceived)
    assert event.data == b"\x01\x02"
    assert event.signal_strength == 87
    assert event.error_margin == 3


def test_a_received_radio_packet_is_queued_as_radio_received_naming_the_sender():
    hw = _hw(radio=_FakeRadio(received=b"\x09", last_sender=42))
    runtime = _runtime(hw)
    tick = build_scene_tick(hw, runtime)

    tick()

    [event] = _queued(runtime, NetworkEvents.RadioReceived)
    assert event.data == b"\x09"
    assert event.sender == "42"


def test_ir_and_radio_are_pumped_every_tick_even_with_no_active_scene():
    hw = _hw(ir=_FakeIr(received=b"\x01"), radio=_FakeRadio(received=b"\x02"))
    runtime = _runtime(hw, active=False)
    tick = build_scene_tick(hw, runtime)

    tick()
    tick()

    assert hw.ir.update_count == 2
    assert hw.radio.update_count == 2


def test_ticking_a_real_scene_delivers_the_sensors_event_to_its_rules():
    """ir_range_transmitter sends on LINE as soon as it sees a sensors event, so
    one tick proves the event reached the scene's rules through manager.update()."""
    network_spy = SpyNetworkControls()
    hw = _hw()
    hw.network_controls = network_spy
    runtime = build_scene_runtime(
        hw, "ir_range_transmitter", scene_registry=scan_boot_scene_registry(None)
    )
    tick = build_scene_tick(hw, runtime)

    tick()

    assert [emitter for _, emitter in network_spy.send_ir_calls] == [LINE]


def test_each_tick_advances_the_scene_and_then_renders_effects_on_the_runtimes_timer():
    hw = _hw()
    runtime = _runtime(hw)
    tick = build_scene_tick(hw, runtime)

    tick()
    tick()

    assert runtime.manager.update_count == 2
    assert runtime.effect_manager.updated_with == [runtime.timer, runtime.timer]


def test_the_ir_telemetry_line_prints_at_most_once_per_second_of_scene_time(capsys):
    hw = _hw(ir=_FakeIr(telemetry="ir: rx=3"))
    runtime = _runtime(hw)
    tick = build_scene_tick(hw, runtime)

    for _ in range(5):
        runtime.timer.total += 0.3
        tick()

    # totals 0.3, 0.6, 0.9, 1.2 (prints), 1.5 -> one line inside the first 1.5 s
    assert capsys.readouterr().out == "ir: rx=3\n"


def test_no_telemetry_prints_when_the_ir_reports_no_change(capsys):
    hw = _hw(ir=_FakeIr(telemetry=None))
    runtime = _runtime(hw)
    tick = build_scene_tick(hw, runtime)

    runtime.timer.total = 5.0
    tick()

    assert capsys.readouterr().out == ""

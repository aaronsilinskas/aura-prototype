from engine.input import AccelerationData
from hardware.shared.polled_sensor import PolledSensor


def _replaying(*reads):
    """A raw read source replaying *reads* in order, where an Exception entry raises."""
    remaining = list(reads)

    def read():
        reading = remaining.pop(0)
        if isinstance(reading, Exception):
            raise reading
        return reading

    return read


def _xyz(sensor: PolledSensor) -> tuple[float, float, float]:
    return (sensor.reading.x, sensor.reading.y, sensor.reading.z)


def test_the_reading_is_the_latest_successful_read():
    sensor = PolledSensor(_replaying((1.0, 2.0, 3.0), (4.0, 5.0, 6.0)), AccelerationData())

    sensor.update()
    sensor.update()

    assert _xyz(sensor) == (4.0, 5.0, 6.0)


def test_a_raising_read_keeps_the_previous_reading():
    sensor = PolledSensor(_replaying((1.0, 2.0, 3.0), OSError(5)), AccelerationData())

    sensor.update()
    sensor.update()

    assert _xyz(sensor) == (1.0, 2.0, 3.0)


def test_a_failed_first_read_leaves_the_reading_zero():
    sensor = PolledSensor(_replaying(OSError(5)), AccelerationData(0.0, 0.0, 0.0))

    sensor.update()

    assert _xyz(sensor) == (0.0, 0.0, 0.0)


def test_the_reading_is_the_same_object_across_updates():
    sensor = PolledSensor(_replaying((1.0, 2.0, 3.0), OSError(5)), AccelerationData())
    reading = sensor.reading

    sensor.update()
    sensor.update()

    assert sensor.reading is reading

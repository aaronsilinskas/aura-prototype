from engine.input import AccelerationData
from engine.log import Logger
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


def _sensor(*reads) -> tuple[PolledSensor, list[str]]:
    """An accelerometer PolledSensor replaying *reads*, and the log fragments it writes."""
    fragments: list[str] = []
    sensor = PolledSensor(
        _replaying(*reads),
        AccelerationData(0.0, 0.0, 0.0),
        "accelerometer",
        Logger("[hw]", fragments.append),
    )
    return sensor, fragments


def _update(sensor: PolledSensor, times: int) -> None:
    for _ in range(times):
        sensor.update()


def _xyz(sensor: PolledSensor) -> tuple[float, float, float]:
    return (sensor.reading.x, sensor.reading.y, sensor.reading.z)


def test_the_reading_is_the_latest_successful_read():
    sensor, _log = _sensor((1.0, 2.0, 3.0), (4.0, 5.0, 6.0))

    sensor.update()
    sensor.update()

    assert _xyz(sensor) == (4.0, 5.0, 6.0)


def test_a_raising_read_keeps_the_previous_reading():
    sensor, _log = _sensor((1.0, 2.0, 3.0), OSError(5))

    sensor.update()
    sensor.update()

    assert _xyz(sensor) == (1.0, 2.0, 3.0)


def test_a_failed_first_read_leaves_the_reading_zero():
    sensor, _log = _sensor(OSError(5))

    sensor.update()

    assert _xyz(sensor) == (0.0, 0.0, 0.0)


def test_the_reading_is_the_same_object_across_updates():
    sensor, _log = _sensor((1.0, 2.0, 3.0), OSError(5))
    reading = sensor.reading

    sensor.update()
    sensor.update()

    assert sensor.reading is reading


def test_a_run_of_failed_reads_logs_one_start_line_carrying_the_first_error():
    sensor, log = _sensor((1.0, 2.0, 3.0), OSError(5), RuntimeError("bus"), OSError(19))

    _update(sensor, 4)

    assert "".join(log) == "[hw] accelerometer read failing: OSError(5)\n"


def test_a_full_run_of_good_reads_logs_one_recovery_line_with_the_failed_and_total_read_counts():
    good = (1.0, 2.0, 3.0)
    sensor, log = _sensor(OSError(5), OSError(5), OSError(5), *[good] * 60)

    _update(sensor, 63)

    assert "".join(log) == (
        "[hw] accelerometer read failing: OSError(5)\n"
        "[hw] accelerometer recovered: 3 of 53 reads failed\n"
    )


def test_alternating_good_and_bad_reads_log_no_recovery_until_a_full_run_of_good_reads():
    good = (1.0, 2.0, 3.0)
    flapping = [good, OSError(5)] * 30
    sensor, log = _sensor(OSError(5), *flapping, *[good] * 49)

    _update(sensor, 1 + 60 + 49)

    assert "".join(log) == "[hw] accelerometer read failing: OSError(5)\n"


def test_a_good_read_while_failing_still_updates_the_reading():
    sensor, _log = _sensor(OSError(5), (4.0, 5.0, 6.0))

    _update(sensor, 2)

    assert _xyz(sensor) == (4.0, 5.0, 6.0)


def test_the_failure_count_is_zero_while_healthy():
    sensor, _log = _sensor((1.0, 2.0, 3.0), (4.0, 5.0, 6.0))

    _update(sensor, 2)

    assert sensor.failed_reads == 0


def test_the_failure_count_is_the_failed_reads_since_the_sensor_started_failing():
    good = (1.0, 2.0, 3.0)
    sensor, _log = _sensor(OSError(5), good, OSError(5), good, good)

    _update(sensor, 5)

    assert sensor.failed_reads == 2


def test_the_failure_count_resets_on_recovery():
    good = (1.0, 2.0, 3.0)
    sensor, _log = _sensor(OSError(5), *[good] * 50)

    _update(sensor, 51)

    assert sensor.failed_reads == 0


def test_a_healthy_sensor_logs_nothing():
    sensor, log = _sensor(*[(1.0, 2.0, 3.0)] * 100)

    _update(sensor, 100)

    assert log == []

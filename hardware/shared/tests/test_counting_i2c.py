"""Tests for CountingI2C — a transparent decorator that tallies I2C byte traffic.

Drives CountingI2C against a fake recording inner bus and asserts observable
totals and forwarded calls, not private attributes.

Prior art: test_matrix_output.py, test_profiling_helpers.py.
"""

import pytest

from hardware.shared.counting_i2c import CountingI2C

# ---------------------------------------------------------------------------
# Fake inner bus — records every call for assertion
# ---------------------------------------------------------------------------


class FakeI2C:
    """Recording fake for the busio.I2C surface that adafruit_bus_device exercises."""

    def __init__(self) -> None:
        self.calls: list = []
        self._locked = False
        self._lock_result = True
        self._scan_result: list = [0x42]

    def try_lock(self) -> bool:
        self.calls.append(("try_lock",))
        self._locked = True
        return self._lock_result

    def unlock(self) -> None:
        self.calls.append(("unlock",))
        self._locked = False

    def writeto(self, address, buffer, *, start=0, end=None) -> None:
        self.calls.append(("writeto", address, bytes(buffer), start, end))

    def readfrom_into(self, address, buffer, *, start=0, end=None) -> None:
        self.calls.append(("readfrom_into", address, start, end))
        # Fill buffer with a recognizable value so callers can verify passthrough
        for i in range(len(buffer)):
            buffer[i] = 0xAB

    def writeto_then_readfrom(
        self,
        address,
        out_buffer,
        in_buffer,
        *,
        out_start=0,
        out_end=None,
        in_start=0,
        in_end=None,
    ) -> None:
        self.calls.append(
            (
                "writeto_then_readfrom",
                address,
                bytes(out_buffer),
                out_start,
                out_end,
                in_start,
                in_end,
            )
        )
        for i in range(len(in_buffer)):
            in_buffer[i] = 0xCD

    def scan(self) -> list:
        self.calls.append(("scan",))
        return self._scan_result

    def deinit(self) -> None:
        self.calls.append(("deinit",))

    def __enter__(self):
        self.calls.append(("__enter__",))
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.calls.append(("__exit__", exc_type, exc_val, exc_tb))
        return False


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake() -> FakeI2C:
    return FakeI2C()


@pytest.fixture()
def counting(fake: FakeI2C) -> CountingI2C:
    return CountingI2C(fake)


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------


def test_counters_start_at_zero_on_construction(fake: FakeI2C) -> None:
    bus = CountingI2C(fake)
    assert bus.bytes_written == 0
    assert bus.bytes_read == 0


# ---------------------------------------------------------------------------
# writeto — byte counting with full and sliced buffers
# ---------------------------------------------------------------------------


class TestWriteto:
    def test_full_buffer_counts_all_bytes(self, counting: CountingI2C, fake: FakeI2C) -> None:
        buf = bytearray(5)
        counting.writeto(0x42, buf)
        assert counting.bytes_written == 5

    def test_sliced_buffer_counts_only_slice_length(
        self, counting: CountingI2C, fake: FakeI2C
    ) -> None:
        buf = bytearray(10)
        counting.writeto(0x42, buf, start=2, end=7)
        assert counting.bytes_written == 5

    def test_start_only_counts_from_start_to_end_of_buffer(
        self, counting: CountingI2C, fake: FakeI2C
    ) -> None:
        buf = bytearray(8)
        counting.writeto(0x42, buf, start=3)
        assert counting.bytes_written == 5

    def test_end_only_counts_from_zero_to_end(self, counting: CountingI2C, fake: FakeI2C) -> None:
        buf = bytearray(8)
        counting.writeto(0x42, buf, end=4)
        assert counting.bytes_written == 4

    def test_forwards_all_arguments_to_inner_bus(
        self, counting: CountingI2C, fake: FakeI2C
    ) -> None:
        buf = bytearray(b"\x01\x02\x03")
        counting.writeto(0x77, buf, start=1, end=3)
        assert ("writeto", 0x77, bytes(buf), 1, 3) in fake.calls

    def test_does_not_increment_bytes_read(self, counting: CountingI2C, fake: FakeI2C) -> None:
        counting.writeto(0x42, bytearray(4))
        assert counting.bytes_read == 0

    def test_accumulates_across_multiple_calls(self, counting: CountingI2C, fake: FakeI2C) -> None:
        counting.writeto(0x42, bytearray(3))
        counting.writeto(0x42, bytearray(5))
        assert counting.bytes_written == 8


# ---------------------------------------------------------------------------
# readfrom_into — byte counting with full and sliced buffers
# ---------------------------------------------------------------------------


class TestReadfromInto:
    def test_full_buffer_counts_all_bytes(self, counting: CountingI2C, fake: FakeI2C) -> None:
        buf = bytearray(6)
        counting.readfrom_into(0x42, buf)
        assert counting.bytes_read == 6

    def test_sliced_buffer_counts_only_slice_length(
        self, counting: CountingI2C, fake: FakeI2C
    ) -> None:
        buf = bytearray(10)
        counting.readfrom_into(0x42, buf, start=1, end=5)
        assert counting.bytes_read == 4

    def test_start_only_counts_from_start_to_end_of_buffer(
        self, counting: CountingI2C, fake: FakeI2C
    ) -> None:
        buf = bytearray(8)
        counting.readfrom_into(0x42, buf, start=2)
        assert counting.bytes_read == 6

    def test_end_only_counts_from_zero_to_end(self, counting: CountingI2C, fake: FakeI2C) -> None:
        buf = bytearray(8)
        counting.readfrom_into(0x42, buf, end=3)
        assert counting.bytes_read == 3

    def test_forwards_all_arguments_to_inner_bus(
        self, counting: CountingI2C, fake: FakeI2C
    ) -> None:
        buf = bytearray(5)
        counting.readfrom_into(0x55, buf, start=0, end=5)
        assert ("readfrom_into", 0x55, 0, 5) in fake.calls

    def test_does_not_increment_bytes_written(self, counting: CountingI2C, fake: FakeI2C) -> None:
        counting.readfrom_into(0x42, bytearray(4))
        assert counting.bytes_written == 0

    def test_accumulates_across_multiple_calls(self, counting: CountingI2C, fake: FakeI2C) -> None:
        counting.readfrom_into(0x42, bytearray(3))
        counting.readfrom_into(0x42, bytearray(7))
        assert counting.bytes_read == 10


# ---------------------------------------------------------------------------
# writeto_then_readfrom — out counts as written, in counts as read
# ---------------------------------------------------------------------------


class TestWritetoThenReadfrom:
    def test_full_buffers_count_written_and_read_separately(
        self, counting: CountingI2C, fake: FakeI2C
    ) -> None:
        out_buf = bytearray(4)
        in_buf = bytearray(6)
        counting.writeto_then_readfrom(0x42, out_buf, in_buf)
        assert counting.bytes_written == 4
        assert counting.bytes_read == 6

    def test_sliced_out_counts_only_out_slice_length_as_written(
        self, counting: CountingI2C, fake: FakeI2C
    ) -> None:
        out_buf = bytearray(10)
        in_buf = bytearray(6)
        counting.writeto_then_readfrom(0x42, out_buf, in_buf, out_start=2, out_end=5)
        assert counting.bytes_written == 3

    def test_out_slice_does_not_affect_bytes_read(
        self, counting: CountingI2C, fake: FakeI2C
    ) -> None:
        out_buf = bytearray(10)
        in_buf = bytearray(6)
        counting.writeto_then_readfrom(0x42, out_buf, in_buf, out_start=2, out_end=5)
        assert counting.bytes_read == 6

    def test_sliced_in_counts_only_in_slice_length_as_read(
        self, counting: CountingI2C, fake: FakeI2C
    ) -> None:
        out_buf = bytearray(4)
        in_buf = bytearray(10)
        counting.writeto_then_readfrom(0x42, out_buf, in_buf, in_start=1, in_end=4)
        assert counting.bytes_read == 3

    def test_in_slice_does_not_affect_bytes_written(
        self, counting: CountingI2C, fake: FakeI2C
    ) -> None:
        out_buf = bytearray(4)
        in_buf = bytearray(10)
        counting.writeto_then_readfrom(0x42, out_buf, in_buf, in_start=1, in_end=4)
        assert counting.bytes_written == 4

    def test_forwards_all_arguments_to_inner_bus(
        self, counting: CountingI2C, fake: FakeI2C
    ) -> None:
        out_buf = bytearray(b"\x01\x02")
        in_buf = bytearray(3)
        counting.writeto_then_readfrom(
            0x33, out_buf, in_buf, out_start=0, out_end=2, in_start=0, in_end=3
        )
        assert (
            "writeto_then_readfrom",
            0x33,
            bytes(out_buf),
            0,
            2,
            0,
            3,
        ) in fake.calls


# ---------------------------------------------------------------------------
# reset() — zeroes both counters; counting resumes afterward
# ---------------------------------------------------------------------------


class TestReset:
    def test_reset_zeroes_bytes_written(self, counting: CountingI2C, fake: FakeI2C) -> None:
        counting.writeto(0x42, bytearray(5))
        counting.reset()
        assert counting.bytes_written == 0

    def test_reset_zeroes_bytes_read(self, counting: CountingI2C, fake: FakeI2C) -> None:
        counting.readfrom_into(0x42, bytearray(5))
        counting.reset()
        assert counting.bytes_read == 0

    def test_counting_resumes_after_reset(self, counting: CountingI2C, fake: FakeI2C) -> None:
        counting.writeto(0x42, bytearray(10))
        counting.reset()
        counting.writeto(0x42, bytearray(3))
        assert counting.bytes_written == 3

    def test_reset_zeroes_both_counters_simultaneously(
        self, counting: CountingI2C, fake: FakeI2C
    ) -> None:
        counting.writeto(0x42, bytearray(5))
        counting.readfrom_into(0x42, bytearray(7))
        counting.reset()
        assert counting.bytes_written == 0
        assert counting.bytes_read == 0


# ---------------------------------------------------------------------------
# try_lock / unlock — return values passed through; no counter change
# ---------------------------------------------------------------------------


class TestTryLockUnlock:
    def test_try_lock_returns_inner_result(self, counting: CountingI2C, fake: FakeI2C) -> None:
        fake._lock_result = True
        assert counting.try_lock() is True

    def test_try_lock_returns_false_when_inner_returns_false(
        self, counting: CountingI2C, fake: FakeI2C
    ) -> None:
        fake._lock_result = False
        assert counting.try_lock() is False

    def test_try_lock_forwards_call_to_inner(self, counting: CountingI2C, fake: FakeI2C) -> None:
        counting.try_lock()
        assert ("try_lock",) in fake.calls

    def test_try_lock_does_not_move_bytes_written(
        self, counting: CountingI2C, fake: FakeI2C
    ) -> None:
        counting.try_lock()
        assert counting.bytes_written == 0

    def test_try_lock_does_not_move_bytes_read(self, counting: CountingI2C, fake: FakeI2C) -> None:
        counting.try_lock()
        assert counting.bytes_read == 0

    def test_unlock_forwards_call_to_inner(self, counting: CountingI2C, fake: FakeI2C) -> None:
        counting.unlock()
        assert ("unlock",) in fake.calls

    def test_unlock_does_not_move_bytes_written(self, counting: CountingI2C, fake: FakeI2C) -> None:
        counting.unlock()
        assert counting.bytes_written == 0

    def test_unlock_does_not_move_bytes_read(self, counting: CountingI2C, fake: FakeI2C) -> None:
        counting.unlock()
        assert counting.bytes_read == 0


# ---------------------------------------------------------------------------
# scan — return value passed through; no counter change
# ---------------------------------------------------------------------------


class TestScan:
    def test_scan_returns_inner_result(self, counting: CountingI2C, fake: FakeI2C) -> None:
        fake._scan_result = [0x10, 0x20]
        result = counting.scan()
        assert result == [0x10, 0x20]

    def test_scan_forwards_call_to_inner(self, counting: CountingI2C, fake: FakeI2C) -> None:
        counting.scan()
        assert ("scan",) in fake.calls

    def test_scan_does_not_move_bytes_written(self, counting: CountingI2C, fake: FakeI2C) -> None:
        counting.scan()
        assert counting.bytes_written == 0

    def test_scan_does_not_move_bytes_read(self, counting: CountingI2C, fake: FakeI2C) -> None:
        counting.scan()
        assert counting.bytes_read == 0


# ---------------------------------------------------------------------------
# deinit — forwards; no counter change
# ---------------------------------------------------------------------------


class TestDeinit:
    def test_deinit_forwards_call_to_inner(self, counting: CountingI2C, fake: FakeI2C) -> None:
        counting.deinit()
        assert ("deinit",) in fake.calls

    def test_deinit_does_not_move_bytes_written(self, counting: CountingI2C, fake: FakeI2C) -> None:
        counting.deinit()
        assert counting.bytes_written == 0

    def test_deinit_does_not_move_bytes_read(self, counting: CountingI2C, fake: FakeI2C) -> None:
        counting.deinit()
        assert counting.bytes_read == 0


# ---------------------------------------------------------------------------
# Context manager — __enter__ / __exit__ forwarded to inner bus
# ---------------------------------------------------------------------------


class TestContextManager:
    def test_enter_returns_counting_i2c_itself(self, counting: CountingI2C, fake: FakeI2C) -> None:
        result = counting.__enter__()
        assert result is counting

    def test_enter_forwards_to_inner(self, counting: CountingI2C, fake: FakeI2C) -> None:
        counting.__enter__()
        assert ("__enter__",) in fake.calls

    def test_exit_forwards_to_inner(self, counting: CountingI2C, fake: FakeI2C) -> None:
        counting.__exit__(None, None, None)
        assert ("__exit__", None, None, None) in fake.calls

    def test_exit_returns_inner_result(self, counting: CountingI2C, fake: FakeI2C) -> None:
        result = counting.__exit__(None, None, None)
        assert result is False

    def test_context_manager_protocol_works_end_to_end(self, fake: FakeI2C) -> None:
        with CountingI2C(fake) as bus:
            assert isinstance(bus, CountingI2C)
        assert ("__enter__",) in fake.calls
        assert any(call[0] == "__exit__" for call in fake.calls)

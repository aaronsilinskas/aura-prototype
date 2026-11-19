"""Tests for the SD-sync wire protocol's helpers that the loopback tests can't isolate."""

from hardware.shared.sd_sync_protocol import iter_chunks


def test_iter_chunks_of_empty_data_yields_no_chunks():
    assert list(iter_chunks(b"")) == []

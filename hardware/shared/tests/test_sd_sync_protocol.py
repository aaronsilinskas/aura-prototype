"""Behaviour tests for the SD-sync line framing and ack check both ends share."""

from collections.abc import Sequence

import pytest

from hardware.shared.sd_sync_protocol import (
    Frame,
    LineFramer,
    Transport,
    delimit_line,
    encode_frame,
    expect_ack,
)


class _ScriptedReads:
    """``read(size)`` callable returning one scripted chunk per call, then nothing."""

    def __init__(self, reads: Sequence[bytes]) -> None:
        self._reads = list(reads)
        self.calls = 0

    def __call__(self, size: int) -> bytes:
        self.calls += 1
        if self._reads:
            return self._reads.pop(0)
        return b""


class _ReplyTransport(Transport):
    """Transport whose ``recv`` returns one scripted reply line."""

    def __init__(self, reply: Frame) -> None:
        self._reply = encode_frame(reply)

    def recv(self) -> bytes:
        return self._reply


def test_delimit_line_terminates_a_line_with_one_newline():
    assert delimit_line(b"YWNrIDAK") == b"YWNrIDAK\n"


def test_read_line_assembles_a_line_split_across_reads():
    framer = LineFramer(_ScriptedReads([b"YW", b"", b"NrIDAK\n"]))

    assert framer.read_line() == b"YWNrIDAK"


def test_read_line_returns_two_lines_from_one_read_without_reading_again():
    read = _ScriptedReads([b"first\nsecond\n"])
    framer = LineFramer(read)

    assert framer.read_line() == b"first"
    assert framer.read_line() == b"second"
    assert read.calls == 1


def test_read_line_keeps_a_partial_next_line_for_the_following_call():
    framer = LineFramer(_ScriptedReads([b"first\nsec", b"ond\n"]))

    assert framer.read_line() == b"first"
    assert framer.read_line() == b"second"


def test_expect_ack_accepts_the_ack_carrying_the_sequence_number():
    expect_ack(_ReplyTransport(Frame("ack", "3")), 3)


@pytest.mark.parametrize(
    "reply",
    [Frame("ack", "2"), Frame("resp", "3"), Frame("chunk", "3", b"x")],
    ids=["wrong-seq", "wrong-kind", "a-chunk"],
)
def test_expect_ack_names_the_expected_and_received_frame_on_any_other_reply(reply):
    with pytest.raises(ValueError) as raised:
        expect_ack(_ReplyTransport(reply), 3)

    assert str(raised.value) == (
        f"expected SD-sync frame 'ack' '3', got {reply.kind!r} {reply.text!r}"
    )


def test_expect_ack_raises_the_callers_error_type():
    class _PeerError(ValueError):
        pass

    with pytest.raises(_PeerError):
        expect_ack(_ReplyTransport(Frame("ack", "0")), 1, error=_PeerError)

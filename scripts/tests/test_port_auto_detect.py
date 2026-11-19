"""Tests for Port auto-detect: which host serial port each channel resolves to.

Enumeration is faked at the toolkit's board enumeration (its ``comports()``), so
the toolkit's own console/data interface filtering runs for real.
"""

import re
from collections.abc import Callable, Sequence

import pytest
from adafruit_board_toolkit import circuitpython_serial
from serial.tools.list_ports_common import ListPortInfo

from scripts.port_auto_detect import PortAutoDetectError, SerialChannel, find_port

_CONSOLE_INTERFACE = "CircuitPython CDC control"
_DATA_INTERFACE = "CircuitPython CDC2 control"


def _usb_port(device: str, interface: str) -> ListPortInfo:
    port = ListPortInfo(device, skip_link_detection=True)
    port.interface = interface
    return port


def _board(console: str, data: "str | None" = None) -> "list[ListPortInfo]":
    ports = [_usb_port(console, _CONSOLE_INTERFACE)]
    if data is not None:
        ports.append(_usb_port(data, _DATA_INTERFACE))
    return ports


@pytest.fixture
def attached(monkeypatch: pytest.MonkeyPatch) -> "Callable[[Sequence[ListPortInfo]], None]":
    def attach(ports: "Sequence[ListPortInfo]") -> None:
        monkeypatch.setattr(circuitpython_serial, "comports", lambda: tuple(ports))

    return attach


@pytest.mark.parametrize(
    ("channel", "expected"),
    [(SerialChannel.CONSOLE, "/dev/cu.usbmodem1101"), (SerialChannel.DATA, "/dev/cu.usbmodem1103")],
)
def test_a_board_with_both_channels_resolves_each_channel_to_its_own_port(
    attached: "Callable[[Sequence[ListPortInfo]], None]", channel: SerialChannel, expected: str
) -> None:
    attached(_board("/dev/cu.usbmodem1101", data="/dev/cu.usbmodem1103"))

    assert find_port(channel) == expected


def test_a_board_without_the_data_channel_still_resolves_the_console_port(
    attached: "Callable[[Sequence[ListPortInfo]], None]",
) -> None:
    attached(_board("/dev/cu.usbmodem1101"))

    assert find_port(SerialChannel.CONSOLE) == "/dev/cu.usbmodem1101"


def test_no_console_port_fails_naming_the_channel_and_the_port_flag(
    attached: "Callable[[Sequence[ListPortInfo]], None]",
) -> None:
    attached([])

    with pytest.raises(
        PortAutoDetectError,
        match=re.escape("no CircuitPython console port found; connect the device or pass --port"),
    ):
        find_port(SerialChannel.CONSOLE)


def test_no_data_port_fails_naming_the_channel_and_the_port_flag(
    attached: "Callable[[Sequence[ListPortInfo]], None]",
) -> None:
    attached(_board("/dev/cu.usbmodem1101"))

    with pytest.raises(
        PortAutoDetectError,
        match=re.escape("no CircuitPython data port found; connect the device or pass --port"),
    ):
        find_port(SerialChannel.DATA)


@pytest.mark.parametrize(
    ("channel", "candidates"),
    [
        (SerialChannel.CONSOLE, "/dev/cu.usbmodem1101, /dev/cu.usbmodem2101"),
        (SerialChannel.DATA, "/dev/cu.usbmodem1103, /dev/cu.usbmodem2103"),
    ],
)
def test_two_boards_fail_listing_both_candidates_and_the_port_flag(
    attached: "Callable[[Sequence[ListPortInfo]], None]", channel: SerialChannel, candidates: str
) -> None:
    attached(
        _board("/dev/cu.usbmodem1101", data="/dev/cu.usbmodem1103")
        + _board("/dev/cu.usbmodem2101", data="/dev/cu.usbmodem2103")
    )

    with pytest.raises(
        PortAutoDetectError,
        match=re.escape(
            f"multiple CircuitPython {channel.value} ports found ({candidates}); "
            "pass --port to select one"
        ),
    ):
        find_port(channel)


@pytest.mark.parametrize("channel", list(SerialChannel))
def test_an_explicit_port_wins_without_scanning_usb(
    monkeypatch: pytest.MonkeyPatch, channel: SerialChannel
) -> None:
    def scan_forbidden() -> "tuple[ListPortInfo, ...]":
        raise AssertionError("an explicit port must not scan USB")

    monkeypatch.setattr(circuitpython_serial, "comports", scan_forbidden)

    assert find_port(channel, explicit_port="/dev/tty.explicit") == "/dev/tty.explicit"

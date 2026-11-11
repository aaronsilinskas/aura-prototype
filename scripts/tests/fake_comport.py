"""A fake pyserial port listing entry, for tests of serial-port selection."""

from typing import cast

from serial.tools.list_ports_common import ListPortInfo


class _FakeComport:
    def __init__(self, device: str) -> None:
        self.device = device


def fake_comport(device: str) -> ListPortInfo:
    """A port listing entry for *device*; selection reads only its ``device``."""
    return cast(ListPortInfo, _FakeComport(device))

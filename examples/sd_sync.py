"""Device-side SD-sync server -- a distinct ``code.py`` entry point, opt-in only.

Mounts the SD card (via ``build_hardware``'s ``SdCardStorage``), then services
the SD-sync protocol (:class:`~hardware.shared.sd_sync_server.SdSyncServer`)
over the USB-CDC *data* channel ``boot.py`` opens
(``usb_cdc.enable(data=True)``) -- kept separate from the console/REPL
channel so file traffic never collides with REPL output or input. Every
request the host sends (``pull``/``push``/``list``) is served in turn by
``SdSyncServer.serve_one``, which dispatches by the request's own verb, so
one connection can carry a mix of requests without the host needing to
reconnect between them.

This app only ever writes the SD card -- it holds no reference to CIRCUITPY
and never imports anything that would let it write flash. Deploying it (via
``scripts/deploy.py examples/sd_sync.py``) is what puts a device into
sync-server mode; deploying any other example is not affected; only the
chosen ``code.py`` decides the mode a device boots into.

This layer -- the byte-frame loop below and the USB-CDC wiring -- is
validated on the bench, not in the CPython test suite (the on-device loop is
exercised in #931); the pieces it composes (``SdSyncServer``, ``SdCardStorage``,
``UsbCdcTransport``) each carry their own board-free or CPython-testable
coverage.

No card fitted
---------------
``aura-device.json`` declaring an ``sdcard`` section is a promise that a card
is physically present. If the card is missing (or otherwise fails to mount),
``build_hardware`` raises -- this app catches that specific failure and
reports "no card detected" over the console rather than crashing into the
REPL, then idles rather than exiting (there is nothing useful left to do).
This is distinct from a device with *no* ``sdcard`` section at all: that
device boots normally and every SD-sync request just replies ``"no_storage"``
(handled already by ``SdSyncServer`` itself), since a card-less device is a
routine configuration, not a fault.

Installation
------------
1. Place ``aura-device.json`` on CIRCUITPY, declaring the SD card's ``sdcard``
   section (``cs``, ``mount``) alongside whatever other hardware the board
   also carries for its normal game examples.
2. Deploy: ``python scripts/deploy.py examples/sd_sync.py`` -- this also
   copies the repo's ``boot.py`` onto the device (paired with every
   ``code.py`` deploy), which is what opens the USB-CDC data channel this
   app reads and writes. A hard reset (not just the deploy's soft reload) is
   required the first time ``boot.py`` lands, since CircuitPython only
   evaluates ``boot.py`` on a hard boot.
3. On the host, drive the data channel with
   :class:`scripts.sd_sync_client.SdSyncClient` over a serial ``Transport``
   pointed at the device's data CDC port.
"""

from __future__ import annotations

import time

import usb_cdc

from engine.log import Logger
from hardware.circuitpython.device_builder import build_hardware, load_device_config
from hardware.circuitpython.usb_cdc_transport import UsbCdcTransport
from hardware.shared.sd_sync_server import SdSyncServer

_IDLE_SECONDS = 1.0

logger = Logger("[sd-sync]")

config = load_device_config()

try:
    hw = build_hardware(config, logger=logger)
except RuntimeError as e:
    if "failed to mount" not in str(e):
        raise  # An unrelated hardware fault -- a real bug, not a routine "no card" case.

    logger.log(f"no card detected -- {e}")
    while True:
        time.sleep(_IDLE_SECONDS)

if hw.storage is None:
    logger.log("no sdcard section configured; every request will reply no_storage")

server = SdSyncServer(hw.storage)
transport = UsbCdcTransport(usb_cdc.data)

logger.log("ready -- servicing SD-sync requests on usb_cdc.data")

while True:
    server.serve_one(transport)

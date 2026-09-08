"""Device-side SD-sync server -- an opt-in ``code.py`` entry point.

Mounts the SD card (via ``build_hardware``'s ``SdCardStorage``) and services
the SD-sync protocol (:class:`~hardware.shared.sd_sync_server.SdSyncServer`)
over the USB-CDC *data* channel ``boot.py`` opens, kept separate from the
console/REPL channel so file traffic never collides with REPL I/O.
``SdSyncServer.serve_one`` dispatches each request by its own verb, so one
connection carries a mix of ``pull``/``push``/``list`` without reconnecting.

Deploying this file (``python scripts/deploy.py examples/sd_sync.py``) is what
puts a device into sync-server mode; the file deployed as ``code.py`` is the
only thing that decides a device's mode.

The byte-frame loop and USB-CDC wiring here are validated on the bench, not in
the CPython suite (the on-device loop is exercised in #931); the pieces it
composes (``SdSyncServer``, ``SdCardStorage``, ``UsbCdcTransport``) each carry
their own board-free or CPython-testable coverage.

No card fitted
--------------
An ``aura-device.json`` with an ``sdcard`` section promises a card is present,
so if it fails to mount ``build_hardware`` raises and this app reports it over
the console and idles rather than crashing into the REPL. This differs from a
device with *no* ``sdcard`` section, which boots normally and replies
``"no_storage"`` to every request (handled by ``SdSyncServer`` itself) -- a
card-less device is a routine configuration, not a fault.

Installation
------------
1. Place ``aura-device.json`` on CIRCUITPY, declaring the SD card's ``sdcard``
   section (``cs``, ``mount``).
2. Deploy: ``python scripts/deploy.py examples/sd_sync.py`` -- this also copies
   the repo's ``boot.py`` (which opens the data channel; see there for the
   first-time hard reset it needs).
3. On the host, drive the device's data CDC port with
   :class:`scripts.sd_sync_client.SdSyncClient`.
"""

from __future__ import annotations

import time

import usb_cdc

from engine.log import Logger
from hardware.circuitpython.device_builder import (
    SdCardMountError,
    build_hardware,
    load_device_config,
)
from hardware.circuitpython.usb_cdc_transport import UsbCdcTransport
from hardware.shared.sd_sync_server import SdSyncServer

_IDLE_SECONDS = 1.0

logger = Logger("[sd-sync]")

config = load_device_config()

try:
    hw = build_hardware(config, logger=logger)
except SdCardMountError as e:
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

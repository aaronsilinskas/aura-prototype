"""Runs once, before ``code.py``, on every boot -- enables the data USB-CDC channel.

``usb_cdc.enable(console=True, data=True)`` opens a *second* USB-serial
endpoint (``usb_cdc.data``) alongside the usual console/REPL one
(``usb_cdc.console``). File traffic -- currently the SD-sync protocol
``examples/sd_sync.py`` speaks -- rides the data channel exclusively, so it
never collides with REPL output or input on the console channel.

This file is deployed by ``scripts/deploy.py`` alongside every example's
``code.py`` (#930): the data channel is harmless and unused by a normal game
example, so shipping it universally avoids a second, easy-to-forget deploy
step and keeps every device's channel layout identical. It has no effect on
which mode a device boots into -- that is decided entirely by which file was
deployed as ``code.py``.

CircuitPython only calls ``usb_cdc.enable`` settings from ``boot.py`` (not
``code.py``); changing this file requires a hard reset (not just a soft
reload) to take effect.
"""

import usb_cdc

usb_cdc.enable(console=True, data=True)

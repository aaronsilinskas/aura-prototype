"""Runs once before ``code.py`` on every boot; enables the USB-CDC *data* channel.

``usb_cdc.enable(console=True, data=True)`` adds a second USB-serial endpoint
(``usb_cdc.data``) so SD-sync file traffic (``examples/sd_sync.py``) never
collides with REPL output or input on the console channel.

Deployed with every example by ``scripts/deploy.py`` (#930), not just the sync
app: the channel is harmless when unused, so shipping it universally avoids an
easy-to-forget second deploy step.

CircuitPython applies ``usb_cdc.enable`` only from ``boot.py``, and only on a
hard reset -- a soft reload will not pick up a change to this file.
"""

import usb_cdc

usb_cdc.enable(console=True, data=True)

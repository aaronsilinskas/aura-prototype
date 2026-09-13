"""Runs once before ``code.py`` on every boot; enables the USB-CDC *data* channel.

``usb_cdc.enable(console=True, data=True)`` adds a second USB-serial endpoint
(``usb_cdc.data``) so SD-sync file traffic (``examples/sd_sync.py``) never
collides with REPL output or input on the console channel.

Deployed with every example by ``scripts/deploy.py`` (#930), not just the sync
app: the channel is harmless when unused, so shipping it universally avoids an
easy-to-forget second deploy step.

CircuitPython applies ``usb_cdc.enable`` only from ``boot.py``, and only on a
hard reset -- a soft reload will not pick up a change to this file.

Special file, special home: this module lives under ``hardware/circuitpython/``
with the other drivers, but ``scripts/deploy.py`` copies it to the mount's
*volume root* as raw ``.py`` -- never compiled, never synced into the mount's
``hardware/circuitpython/`` subtree -- because the volume root is the only
location and form in which CircuitPython will execute it.
"""

import usb_cdc

usb_cdc.enable(console=True, data=True)

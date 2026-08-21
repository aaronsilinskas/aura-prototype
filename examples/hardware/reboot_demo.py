"""On-device round-trip check for the reboot seam (#913).

Exercises the hardware-boundary behaviour the CPython suite cannot: that a
scene selection written to ``aura-state.json`` actually survives
``microcontroller.reset()`` and is read back by the boot resolver on the next
boot. A rule triggers a reboot only through downstream lobby work, so this
example drives the live adapter
(:class:`~hardware.circuitpython.device_reboot.DeviceSceneReboot`) directly --
the smallest end-to-end exercise of the seam on real hardware. Keep it around
as a regression check to re-run whenever the reboot path, the state store, or
the boot resolver changes.

``microcontroller.reset()`` re-runs this same ``code.py``, so this example is
idempotent across resets by recording its own progress under a dedicated
``reboot_demo_phase`` key in ``aura-state.json`` (a fresh boot has none). That
yields a self-terminating three-boot cycle that proves the whole seam in a
single deploy:

- **Boot 1** (no phase): resolve + print the boot scene (the flash
  ``default_scene``), record ``phase=into``, then ``reboot_into(TARGET_SCENE)``
  -- writes ``scene=TARGET_SCENE`` and ``return_to=<booted scene>``, then
  hard-resets.
- **Boot 2** (``phase=into``; scene now resolves to ``TARGET_SCENE``, with
  ``return_to`` recorded): print it -- this is the proof the write survived the
  reset and the boot resolver read the override -- record ``phase=previous``,
  then ``reboot_to_previous()`` -- writes ``scene=<recorded return_to>``, clears
  ``return_to``, and hard-resets.
- **Boot 3** (``phase=previous``; scene back to the original, ``return_to``
  cleared): print, clear the phase key, then stop -- proving the ``return_to``
  round-trip and its ``clear``, and leaving the card clean to re-run.

The ``phase`` key is written before each ``reboot_*`` call, so the adapter's own
``scene``/``return_to`` writes (read-modify-write) preserve it across the reset;
the boot resolver ignores the extra key.

Each boot prints a distinctive ``__REBOOT`` marker so the three boots are
unmistakable in the serial log.

Capturing serial across the resets
----------------------------------
``scripts/deploy_watch.py`` will NOT span this cleanly: it opens one serial
connection and waits for the post-deploy reboot banner, but
``microcontroller.reset()`` re-enumerates USB CDC mid-run and drops the port on
each cycle. Deploy once with ``scripts/deploy.py`` and watch the console
manually (Mu / ``tio`` / ``screen``) across the three boots::

    python scripts/deploy.py examples/hardware/reboot_demo.py

Requires the same deployed ``aura-device.json`` + ``aura-settings.json`` as
``scene_demo.py``, a mounted SD card (the whole point -- a card-less device
logs and never reboots), and a ``TARGET_SCENE`` below that is present in the
scene registry and differs from the ``default_scene`` so the boot-2 switch is
visible. It leaves the card clean on completion, so re-running is just another
deploy.
"""

from __future__ import annotations

import time

from app.scene_composition import resolve_boot_scene_name
from engine.log import Logger
from engine.scene import SceneRegistry
from hardware.circuitpython.device_builder import build_hardware, load_device_config
from hardware.circuitpython.device_reboot import DeviceSceneReboot
from hardware.shared.device_settings import read_settings_mapping
from hardware.shared.device_state import DeviceStateStore

# The scene reboot_into() switches to. Must be in the registry and, for the
# proof to be visible, different from the flash default_scene the device boots.
TARGET_SCENE = "red_light_green_light"

# Seconds each boot pauses before rebooting, so the serial log is readable.
_HOLD_SECONDS = 3.0


def _hold(logger: Logger, why: str) -> None:
    logger.log(f"holding {_HOLD_SECONDS:.0f}s before {why} ...")
    time.sleep(_HOLD_SECONDS)


scene_registry = SceneRegistry()
scene_registry.scan_dir("packs/scenes", "packs.scenes")

config = load_device_config()
hw_logger = Logger("[hw]")
hw = build_hardware(config, logger=hw_logger)

settings_mapping = read_settings_mapping()
scene_name = resolve_boot_scene_name(scene_registry, hw.storage, settings_mapping, logger=hw_logger)

# This example owns reboot_demo_phase; return_to is the seam's own key, read
# here only to print as proof (the adapter is what writes and clears it).
state = DeviceStateStore(hw.storage, hw_logger)
phase = state.get("reboot_demo_phase")
return_to = state.get("return_to")

reboot = DeviceSceneReboot(hw.storage, booted_scene=scene_name, logger=hw_logger)

if hw.storage is None:
    # Card-less: the adapter would only log-and-return, so there's nothing to
    # round-trip. Say so loudly rather than silently sitting on boot 1 forever.
    print(f"__REBOOT boot=? scene={scene_name!r} storage=None (card-less; nothing to test)")
elif phase is None:
    print(f"__REBOOT boot=1 phase=None scene={scene_name!r} -- will reboot_into({TARGET_SCENE!r})")
    state.set("reboot_demo_phase", "into")
    _hold(hw_logger, f"reboot_into({TARGET_SCENE!r})")
    reboot.reboot_into(TARGET_SCENE)
    print("__REBOOT ERROR: reboot_into returned without resetting")
elif phase == "into":
    # The criterion's proof: after the reset the resolver picked up the override.
    print(f"__REBOOT boot=2 phase=into scene={scene_name!r} return_to={return_to!r}")
    print("__REBOOT boot=2 override survived the reset; will reboot_to_previous()")
    state.set("reboot_demo_phase", "previous")
    _hold(hw_logger, "reboot_to_previous()")
    reboot.reboot_to_previous()
    print("__REBOOT ERROR: reboot_to_previous returned without resetting")
else:  # phase == "previous"
    print(f"__REBOOT boot=3 phase=previous scene={scene_name!r} return_to={return_to!r}")
    print("__REBOOT boot=3 round-trip complete, stopping")
    state.clear("reboot_demo_phase")

while True:
    time.sleep(1.0)

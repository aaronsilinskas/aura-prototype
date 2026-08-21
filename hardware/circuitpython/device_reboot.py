"""DeviceSceneReboot — the live SceneReboot backed by microcontroller.reset().

The only module that calls ``microcontroller.reset()``. Imported only from
``app.scene_runtime`` (device-only), which constructs it with the scene name
the process booted into plus ``hw.storage``, then hands it to
``build_scene_runtime`` as the board-free ``SceneReboot`` port. Unlike
``rfm69_radio_transport``/``sdcard_storage``, ``microcontroller`` needs no
deferred import to keep an optional peripheral library uninstalled — it is a
core CircuitPython module, always present.
"""

from __future__ import annotations

import microcontroller

from engine.log import Logger
from engine.state import SceneReboot
from hardware.shared.device_state import DeviceStateStore
from hardware.shared.device_storage import DeviceStorage

__all__ = ["DeviceSceneReboot"]


class DeviceSceneReboot(SceneReboot):
    """Live ``SceneReboot``: persists via a composed ``DeviceStateStore``, then resets.

    Holds *storage* itself (not just the ``DeviceStateStore`` composed over
    it) so it knows whether persistence is available: on a card-less device
    (``storage is None``, where ``DeviceStateStore.set`` is a silent no-op)
    this adapter does not reboot at all for either method — it logs and
    returns, leaving the caller running, since persisting nothing and then
    resetting would boot into whatever ``aura-settings.json`` already
    defaults to and silently discard the request (v1 gives no on-device
    visual for this failure).

    Args:
        storage: The mounted ``DeviceStorage`` to persist through, or None
            on a card-less device.
        booted_scene: The name of the scene this process booted into.
            Recorded as ``return_to`` by :meth:`reboot_into`, so no rule
            needs to know its own scene name — the return target is "the
            scene being left," known automatically at construction.
        logger: Where a card-less or no-``return_to`` no-op is logged.
            Omitted or None normalizes to ``Logger.SILENT``.
    """

    __slots__ = ("_booted_scene", "_logger", "_state_store", "_storage")

    def __init__(
        self,
        storage: DeviceStorage | None,
        booted_scene: str,
        logger: Logger | None = None,
    ) -> None:
        self._storage = storage
        self._booted_scene = booted_scene
        self._logger = logger if logger is not None else Logger.SILENT
        self._state_store = DeviceStateStore(storage, self._logger)

    def reboot_into(self, target: str) -> None:
        """Persist ``scene=target``/``return_to=<booted scene>``, then reset.

        A card-less device logs and returns instead of rebooting — see the
        class docstring.
        """
        if self._storage is None:
            self._logger.log(f"no SD card mounted; not rebooting into scene {target!r}")
            return
        self._state_store.set("scene", target)
        self._state_store.set("return_to", self._booted_scene)
        microcontroller.reset()

    def reboot_to_previous(self) -> None:
        """Persist the recorded ``return_to`` as ``scene``, clear it, then reset.

        A no-op (logged) when no ``return_to`` was recorded, or on a
        card-less device — see the class docstring for the latter.
        """
        if self._storage is None:
            self._logger.log("no SD card mounted; not rebooting to the previous scene")
            return
        return_to = self._state_store.get("return_to")
        if return_to is None:
            self._logger.log("no return_to recorded; not rebooting")
            return
        self._state_store.set("scene", return_to)
        self._state_store.clear("return_to")
        microcontroller.reset()

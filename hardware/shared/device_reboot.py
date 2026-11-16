"""DeviceSceneReboot — the live SceneReboot: persist the target, then reset.

Board-free: the reset is injected rather than imported, so the adapter runs
under CPython. ``app.scene_composition.build_scene_boot`` builds it with the
reset it is handed (on a board, ``run_scene`` passes ``microcontroller.reset``)
and wires it into the booted scene as its ``SceneReboot`` port.
"""

from __future__ import annotations

from engine.log import Logger
from engine.state import SceneReboot
from hardware.shared.persisted_scene import PersistedScene

TYPE_CHECKING = False

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["DeviceSceneReboot"]


class DeviceSceneReboot(SceneReboot):
    """Live ``SceneReboot``: records the switch through ``PersistedScene``, then resets.

    On a card-less device (*persisted_scene* is ``None``) it does not reboot
    at all for either method — it logs and returns, leaving the caller
    running, since persisting nothing and then resetting would boot into
    whatever ``aura-boot.json`` already defaults to and silently discard the
    request (v1 gives no on-device visual for this failure).

    Args:
        persisted_scene: The card's Persisted scene record, or ``None`` on a
            card-less device.
        booted_scene: The name of the scene this process booted into.
            Recorded as ``return_to`` by :meth:`reboot_into`, so no rule
            needs to know its own scene name — the return target is "the
            scene being left," known automatically at construction.
        reset: Resets the device. On a board this is
            ``microcontroller.reset``, which never returns.
        logger: Where a card-less or no-``return_to`` no-op is logged.
            Omitted or None normalizes to ``Logger.SILENT``.
    """

    __slots__ = ("_booted_scene", "_logger", "_persisted_scene", "_reset")

    def __init__(
        self,
        persisted_scene: PersistedScene | None,
        booted_scene: str,
        reset: Callable[[], None],
        logger: Logger | None = None,
    ) -> None:
        self._persisted_scene = persisted_scene
        self._booted_scene = booted_scene
        self._reset = reset
        self._logger = logger if logger is not None else Logger.SILENT

    def reboot_into(self, target: str) -> None:
        """Record a Reboot into *target*, leaving the booted scene, then reset.

        A card-less device logs and returns instead of rebooting — see the
        class docstring.
        """
        if self._persisted_scene is None:
            self._logger.log(f"no SD card mounted; not rebooting into scene {target!r}")
            return
        self._persisted_scene.record_reboot(target, self._booted_scene)
        self._reset()

    def reboot_to_previous(self) -> None:
        """Record a return to the recorded ``return_to``, then reset.

        A no-op (logged) when no ``return_to`` was recorded, or on a
        card-less device — see the class docstring for the latter.
        """
        if self._persisted_scene is None:
            self._logger.log("no SD card mounted; not rebooting to the previous scene")
            return
        if self._persisted_scene.record_return() is None:
            self._logger.log("no return_to recorded; not rebooting")
            return
        self._reset()

    def previous_scene(self) -> str | None:
        """The recorded ``return_to``, or ``None`` when none is, or on a card-less device."""
        if self._persisted_scene is None:
            return None
        return self._persisted_scene.previous_scene()

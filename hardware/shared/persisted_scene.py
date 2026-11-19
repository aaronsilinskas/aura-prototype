"""PersistedScene -- the Persisted scene record on the card, and the only code that names its keys.

The record is the Persisted scene, its ``return_to`` companion and the
recorded Scene deploy token, kept in ``aura-state.json`` under the reserved
``persisted_scene.`` prefix so game data in the same file never collides with
it (ADR-0009). An older card's unprefixed ``scene`` / ``return_to`` keys are
ignored.
"""

from __future__ import annotations

from engine.log import Logger
from hardware.shared.device_state import DeviceStateStore
from hardware.shared.scene_selection import SCENE_DEPLOY_TOKEN_KEY, non_empty_string_or_none

TYPE_CHECKING = False

if TYPE_CHECKING:
    from typing import Final

__all__ = ["PersistedScene"]

_SCENE_KEY: Final = "persisted_scene.scene"
_RETURN_TO_KEY: Final = "persisted_scene.return_to"
_DEPLOY_TOKEN_KEY: Final = "persisted_scene.deploy_token"


class PersistedScene:
    """Reads and changes the Persisted scene record; each change is one store write.

    Args:
        store: The boot's one ``DeviceStateStore``; on a card-less device it
            reads empty and drops writes, so the record is always empty.
        logger: Where an applied Scene deploy is logged. Omitted or None
            normalizes to ``Logger.SILENT``.
    """

    __slots__ = ("_logger", "_store")

    def __init__(self, store: DeviceStateStore, logger: Logger | None = None) -> None:
        self._store = store
        self._logger = logger if logger is not None else Logger.SILENT

    def apply_scene_deploy(self, boot_mapping: dict) -> None:
        """Apply *boot_mapping*'s Scene deploy token to the record, if not yet applied.

        A new token clears the Persisted scene and its ``return_to`` and is
        recorded, in one write, and the deploy is logged. An absent, empty or
        already recorded token changes nothing.
        """
        token = non_empty_string_or_none(boot_mapping.get(SCENE_DEPLOY_TOKEN_KEY))
        if token is None:
            return
        state = self._store.read()
        if state.get(_DEPLOY_TOKEN_KEY) == token:
            return
        persisted = state.pop(_SCENE_KEY, None)
        state.pop(_RETURN_TO_KEY, None)
        state[_DEPLOY_TOKEN_KEY] = token
        if not self._store.write(state):
            return
        cleared = "no Persisted scene to clear" if persisted is None else f"cleared {persisted!r}"
        deployed = boot_mapping.get("default_scene")
        self._logger.log(f"scene deploy {token} applied: booting {deployed!r}, {cleared}")

    def boot_candidates(self, boot_mapping: dict) -> tuple[str | None, str]:
        """Return ``(persisted, fallback)``: the scene to try first, and the one to boot otherwise.

        *fallback* is flash ``default_scene``, or the Persisted scene when no
        default is set. *persisted* is the Persisted scene when a different
        default stands behind it, else ``None``.

        Args:
            boot_mapping: The raw ``aura-boot.json`` mapping.

        Raises:
            ValueError: Neither the Persisted scene nor a flash
                ``default_scene`` is a non-empty string.
        """
        persisted = non_empty_string_or_none(self._store.get(_SCENE_KEY))
        default = non_empty_string_or_none(boot_mapping.get("default_scene"))
        if default is None or default == persisted:
            if persisted is None:
                raise ValueError(
                    "no boot scene: neither a Persisted scene (aura-state.json) nor a flash "
                    + "'default_scene' (aura-boot.json) is set"
                )
            return None, persisted
        return persisted, default

    def record_reboot(self, target: str, left: str) -> None:
        """Record a Reboot into *target*, with *left*, the scene being left, as ``return_to``."""
        self._store.update({_SCENE_KEY: target, _RETURN_TO_KEY: left})

    def record_return(self) -> str | None:
        """Make the recorded ``return_to`` the Persisted scene and clear it; return it.

        Returns ``None``, writing nothing, when no ``return_to`` is recorded.
        """
        target = self.previous_scene()
        if target is None:
            return None
        self._store.update({_SCENE_KEY: target}, remove=(_RETURN_TO_KEY,))
        return target

    def previous_scene(self) -> str | None:
        """The recorded ``return_to``, or ``None`` when none is."""
        return non_empty_string_or_none(self._store.get(_RETURN_TO_KEY))

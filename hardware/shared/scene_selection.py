"""Pure scene-name resolution for aura-boot.json — no board imports, CPython-testable."""

from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass

from engine.log import Logger
from hardware.shared.device_state import DeviceStateStore
from hardware.shared.device_storage import DeviceStorage

__all__ = [
    "SCENE_DEPLOY_TOKEN_KEY",
    "apply_scene_deploy",
    "boot_scene_candidates",
    "resolve_scene_name",
    "with_scene_deploy",
]

SCENE_DEPLOY_TOKEN_KEY: Final = "scene_deploy_token"


def _non_empty_string_or_none(value: object) -> str | None:
    """Return *value* unchanged when it is a non-empty string, else None.

    Shared by both scene-name legs below: a present-but-wrong-typed or
    empty-string value is treated the same as an absent one, never as its
    own error case.
    """
    return value if isinstance(value, str) and value else None


def resolve_scene_name(boot_mapping: dict) -> str:
    """Return the configured ``default_scene``, or raise when none is set.

    There is no code-level fallback scene, so ``aura-boot.json`` must
    declare a non-empty ``default_scene`` string or resolution fails.  This
    helper does no registry lookup — verifying the name against the available
    scenes is the runtime's job.

    Args:
        boot_mapping: The raw ``aura-boot.json`` mapping.
    """
    raw = boot_mapping.get("default_scene")
    scene = _non_empty_string_or_none(raw)
    if scene is not None:
        return scene
    raise ValueError(f"aura-boot.json 'default_scene' must be a non-empty string, got {raw!r}")


def with_scene_deploy(boot_values: dict, scene: str, token: str) -> dict:
    """Return a copy of *boot_values* deploying *scene* under the Scene deploy token *token*.

    Every other boot value is kept. The caller supplies *token*, fresh per
    deploy, so nothing on the device needs a random source.
    """
    written = dict(boot_values)
    written["default_scene"] = scene
    written[SCENE_DEPLOY_TOKEN_KEY] = token
    return written


def apply_scene_deploy(
    storage: DeviceStorage | None,
    boot_mapping: dict,
    logger: Logger | None = None,
) -> None:
    """Apply *boot_mapping*'s Scene deploy token to the card, if not yet applied.

    Args:
        storage: The mounted ``DeviceStorage``, or ``None`` on a card-less device.
        boot_mapping: The raw ``aura-boot.json`` mapping.
        logger: Where the applied-token line and any fail-soft state read
            are logged; omitted, nothing is logged.
    """
    token = _non_empty_string_or_none(boot_mapping.get(SCENE_DEPLOY_TOKEN_KEY))
    if token is None or storage is None:
        return
    logger = logger if logger is not None else Logger.SILENT
    store = DeviceStateStore(storage, logger)
    state = store.read()
    if state.get(SCENE_DEPLOY_TOKEN_KEY) == token:
        return
    persisted = state.pop("scene", None)
    state.pop("return_to", None)
    state[SCENE_DEPLOY_TOKEN_KEY] = token
    store.write(state)
    cleared = "no Persisted scene to clear" if persisted is None else f"cleared {persisted!r}"
    deployed = boot_mapping.get("default_scene")
    logger.log(f"scene deploy {token} applied: booting {deployed!r}, {cleared}")


def boot_scene_candidates(
    storage: DeviceStorage | None,
    boot_mapping: dict,
    logger: Logger | None = None,
) -> tuple[str | None, str]:
    """Return ``(persisted, fallback)``: the boot scene to try first, and the one to boot otherwise.

    *fallback* is flash ``default_scene``, or the Persisted scene when no
    default is set. *persisted* is the Persisted scene when a different
    default stands behind it, else ``None``.

    Args:
        storage: The mounted ``DeviceStorage`` to read the Persisted scene
            through, or ``None`` on a card-less device (treated as having none).
        boot_mapping: The raw ``aura-boot.json`` mapping.
        logger: Where a fail-soft persisted-state read is logged; forwarded
            to :class:`DeviceStateStore`.

    Raises:
        ValueError: Neither a persisted SD ``scene`` nor a flash
            ``default_scene`` is a non-empty string.
    """
    persisted = _non_empty_string_or_none(DeviceStateStore(storage, logger).get("scene"))
    default = _non_empty_string_or_none(boot_mapping.get("default_scene"))
    if default is None or default == persisted:
        if persisted is None:
            raise ValueError(
                "no boot scene: neither a persisted SD 'scene' (aura-state.json) nor a flash "
                + "'default_scene' (aura-boot.json) is set"
            )
        return None, persisted
    return persisted, default

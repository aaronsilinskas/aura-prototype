"""Pure scene-name resolution for aura-settings.json — no board imports, CPython-testable."""

from __future__ import annotations

from engine.log import Logger
from hardware.shared.device_state import DeviceStateStore
from hardware.shared.device_storage import DeviceStorage

__all__ = ["apply_scene_deploy", "resolve_boot_scene", "resolve_scene_name"]


def _non_empty_string_or_none(value: object) -> str | None:
    """Return *value* unchanged when it is a non-empty string, else None.

    Shared by both scene-name legs below: a present-but-wrong-typed or
    empty-string value is treated the same as an absent one, never as its
    own error case.
    """
    return value if isinstance(value, str) and value else None


def resolve_scene_name(settings_mapping: dict) -> str:
    """Return the configured ``default_scene``, or raise when none is set.

    There is no code-level fallback scene, so ``aura-settings.json`` must
    declare a non-empty ``default_scene`` string or resolution fails.  This
    helper does no registry lookup — verifying the name against the available
    scenes is the runtime's job.

    Args:
        settings_mapping: The raw ``aura-settings.json`` mapping.
    """
    raw = settings_mapping.get("default_scene")
    scene = _non_empty_string_or_none(raw)
    if scene is not None:
        return scene
    raise ValueError(f"aura-settings.json 'default_scene' must be a non-empty string, got {raw!r}")


def apply_scene_deploy(
    storage: DeviceStorage | None,
    settings_mapping: dict,
    logger: Logger | None = None,
) -> None:
    """Apply a pending Scene deploy token: clear the Persisted scene once per deploy.

    ``deploy.py --scene`` writes a fresh ``scene_deploy_token`` beside
    ``default_scene`` in *settings_mapping*. When that token is a non-empty
    string that differs from the one recorded in the card's
    ``aura-state.json``, the Persisted scene (``scene`` and ``return_to``) is
    removed and the token recorded, in one write, so the next resolution
    falls through to the deployed ``default_scene``. Applying logs one line;
    an absent or invalid token, a card-less device, or an already-applied
    token is a silent no-op. The deployed scene is not checked against any
    registry -- an unknown one fails at resolution, as a bad
    ``default_scene`` always has.

    Args:
        storage: The mounted ``DeviceStorage``, or None on a card-less device.
        settings_mapping: The raw ``aura-settings.json`` mapping.
        logger: Where the applied-token line and any fail-soft state read
            are logged; omitted, nothing is logged.
    """
    token = _non_empty_string_or_none(settings_mapping.get("scene_deploy_token"))
    if token is None or storage is None:
        return
    logger = logger if logger is not None else Logger.SILENT
    store = DeviceStateStore(storage, logger)
    if store.get("scene_deploy_token") == token:
        return
    persisted = store.get("scene")
    store.update({"scene_deploy_token": token}, remove=("scene", "return_to"))
    cleared = "no Persisted scene to clear" if persisted is None else f"cleared {persisted!r}"
    deployed = settings_mapping.get("default_scene")
    logger.log(f"scene deploy {token} applied: booting {deployed!r}, {cleared}")


def resolve_boot_scene(
    storage: DeviceStorage | None,
    settings_mapping: dict,
    logger: Logger | None = None,
) -> str:
    """Resolve the boot scene: persisted SD ``scene`` -> flash ``default_scene`` -> raise.

    Composes the SD-persisted override (read via a :class:`DeviceStateStore`
    over *storage*) with the flash-authored default (*settings_mapping*'s
    ``default_scene``, as read by :func:`read_settings_mapping`). The two
    files key the scene under different names, so each value independently
    goes through :func:`_non_empty_string_or_none` rather than delegating to
    :func:`resolve_scene_name`, which is hardwired to the flash key and
    always raises when its key is absent — behaviour this resolver only
    wants when *both* legs are absent.

    Args:
        storage: The mounted ``DeviceStorage`` to read the persisted override
            through, or None on a card-less device (treated as no override).
        settings_mapping: The raw ``aura-settings.json`` mapping.
        logger: Where a fail-soft persisted-state read is logged; forwarded
            to :class:`DeviceStateStore`.

    Raises:
        ValueError: Neither a persisted SD ``scene`` nor a flash
            ``default_scene`` is a non-empty string.
    """
    persisted = _non_empty_string_or_none(DeviceStateStore(storage, logger).get("scene"))
    if persisted is not None:
        return persisted
    default = _non_empty_string_or_none(settings_mapping.get("default_scene"))
    if default is not None:
        return default
    raise ValueError(
        "no boot scene: neither a persisted SD 'scene' (aura-state.json) nor a flash "
        + "'default_scene' (aura-settings.json) is set"
    )

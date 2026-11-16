"""The flash side of scene selection: ``aura-boot.json``'s ``default_scene`` and Scene deploy token.

Pure and board-free. The card side, the Persisted scene record, is
``hardware.shared.persisted_scene``.
"""

from __future__ import annotations

TYPE_CHECKING = False

if TYPE_CHECKING:
    from typing import Final

__all__ = [
    "SCENE_DEPLOY_TOKEN_KEY",
    "non_empty_string_or_none",
    "resolve_scene_name",
    "with_scene_deploy",
]

SCENE_DEPLOY_TOKEN_KEY: Final = "scene_deploy_token"


def non_empty_string_or_none(value: object) -> str | None:
    """Return *value* unchanged when it is a non-empty string, else None.

    A present-but-wrong-typed or empty-string value is treated the same as
    an absent one, never as its own error case.
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
    scene = non_empty_string_or_none(raw)
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

"""Pure scene-name resolution for aura-settings.json — no board imports, CPython-testable."""

from __future__ import annotations

__all__ = ["resolve_scene_name"]


def resolve_scene_name(settings_mapping: dict) -> str:
    """Return the configured ``default_scene``, or raise when none is set.

    There is no code-level fallback scene, so ``aura-settings.json`` must
    declare a non-empty ``default_scene`` string or resolution fails.  This
    helper does no registry lookup — verifying the name against the available
    scenes is the runtime's job.

    Args:
        settings_mapping: The raw ``aura-settings.json`` mapping.
    """
    scene = settings_mapping.get("default_scene")
    if isinstance(scene, str) and scene:
        return scene
    raise ValueError(
        f"aura-settings.json 'default_scene' must be a non-empty string, got {scene!r}"
    )

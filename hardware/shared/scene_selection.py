"""Pure scene-name resolution for aura-device.json — no board imports, CPython-testable."""

from __future__ import annotations

__all__ = ["resolve_scene_name"]


def resolve_scene_name(config_mapping: dict) -> str:
    """Return the requested scene name, raising when none is configured.

    The ``"scene"`` value is honoured only when it is a non-empty string; a
    missing, empty, or non-string value raises ``ValueError`` — there is no
    code-level default scene, so ``aura-device.json`` must declare one
    explicitly.  This helper does no registry lookup — verifying the name
    against the available scenes is the runtime's job.

    Args:
        config_mapping: The raw ``aura-device.json`` mapping.
    """
    scene = config_mapping.get("scene")
    if isinstance(scene, str) and scene:
        return scene
    raise ValueError(f"aura-device.json 'scene' must be a non-empty string, got {scene!r}")

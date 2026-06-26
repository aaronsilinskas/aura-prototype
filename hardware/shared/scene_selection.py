"""Pure scene-name resolution for aura-device.json — no board imports, CPython-testable."""

from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass

__all__ = ["DEFAULT_SCENE", "resolve_scene_name"]

DEFAULT_SCENE: Final = "hardware_test"


def resolve_scene_name(config_mapping: dict) -> str:
    """Return the requested scene name, or ``DEFAULT_SCENE`` when none is configured.

    The ``"scene"`` value is honoured only when it is a non-empty string; a
    missing, empty, or non-string value falls back to ``DEFAULT_SCENE``.  This
    helper does no registry lookup — verifying the name against the available
    scenes is the runtime's job.

    Args:
        config_mapping: The raw ``aura-device.json`` mapping.
    """
    scene = config_mapping.get("scene")
    if isinstance(scene, str) and scene:
        return scene
    return DEFAULT_SCENE

"""The Capability vocabulary and the Capability errors.

Board-free: the scan, the device's Capabilities, the run-time check and the
Simulation test harness all name Capabilities through this module.
"""

from __future__ import annotations

__all__ = [
    "MissingCapabilityError",
    "UnknownCapabilityError",
    "is_capability",
]

from engine.scan_error import PackScanError

# Every Capability except ``button.<label>``, whose labels are open-ended.
_FIXED_CAPABILITIES = frozenset(
    (
        "ir.line",
        "ir.cone",
        "ir.area_of_effect",
        "ir.receive",
        "radio",
        "storage",
        "accelerometer",
        "magnetometer",
    )
)

_BUTTON_PREFIX = "button."


def is_capability(name: object) -> bool:
    """Whether *name* is in the Capability vocabulary.

    ``button.<label>`` takes a button label, ``A`` to ``Z``.
    """
    if not isinstance(name, str):
        return False
    if name in _FIXED_CAPABILITIES:
        return True
    if not name.startswith(_BUTTON_PREFIX):
        return False
    label = name[len(_BUTTON_PREFIX) :]
    return len(label) == 1 and "A" <= label <= "Z"


class UnknownCapabilityError(PackScanError):
    """A ``requires`` list in *path* names *name*, which is not a Capability."""

    def __init__(self, path: str, name: object) -> None:
        self.path = path
        self.name = name
        super().__init__(f"'{path}' requires {name!r}, which is not a Capability")


class MissingCapabilityError(ValueError):
    """The device lacks *capabilities*, which *scene* (``None`` for a send) needs now."""

    def __init__(self, capabilities: frozenset[str], scene: str | None) -> None:
        self.capabilities = capabilities
        self.scene = scene
        missing = ", ".join(sorted(capabilities))
        if scene is None:
            super().__init__(f"The device lacks {missing}")
        else:
            super().__init__(f"Scene '{scene}' needs {missing}, which the device lacks")

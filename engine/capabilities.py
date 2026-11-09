"""The Capability vocabulary and the Capability errors.

Board-free: the scan, the device's Capabilities, the run-time check and the
Simulation test harness all name Capabilities through this module.
"""

from __future__ import annotations

__all__ = [
    "IR_RECEIVE",
    "Capabilities",
    "MissingCapabilityError",
    "UnknownCapabilityError",
    "button_capability",
    "button_label_of",
    "describe_capabilities",
    "ir_emitter_capability",
    "ir_emitter_of",
    "is_capability",
    "unknown_capabilities",
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

IR_RECEIVE = "ir.receive"

_BUTTON_PREFIX = "button."
_IR_PREFIX = "ir."


def button_capability(label: str) -> str:
    """The Capability of having the button labelled *label*."""
    return _BUTTON_PREFIX + label


def button_label_of(name: str) -> str | None:
    """The button label in the ``button.<label>`` Capability *name*; ``None`` for any other."""
    if not name.startswith(_BUTTON_PREFIX):
        return None
    label = name[len(_BUTTON_PREFIX) :]
    return label if len(label) == 1 and "A" <= label <= "Z" else None


def ir_emitter_capability(emitter: str) -> str:
    """The Capability of having IR emitter *emitter* (``engine.network.LINE`` and the like)."""
    return _IR_PREFIX + emitter


def ir_emitter_of(name: str) -> str | None:
    """The IR emitter in the ``ir.<emitter>`` Capability *name*; ``None`` for any other."""
    if name == IR_RECEIVE or name not in _FIXED_CAPABILITIES or not name.startswith(_IR_PREFIX):
        return None
    return name[len(_IR_PREFIX) :]


def is_capability(name: object) -> bool:
    """Whether *name* is in the Capability vocabulary.

    ``button.<label>`` takes a button label, ``A`` to ``Z``.
    """
    if not isinstance(name, str):
        return False
    return name in _FIXED_CAPABILITIES or button_label_of(name) is not None


def unknown_capabilities(names: list) -> list:
    """The items of *names* outside the Capability vocabulary, in order."""
    return [name for name in names if not is_capability(name)]


def describe_capabilities(names: frozenset[str]) -> str:
    """*names* sorted and comma-joined, for a message."""
    return ", ".join(sorted(names))


class Capabilities:
    """A read-only view of the Capabilities a device has, for rules to ask about.

    Reached as ``state.capabilities``.
    """

    __slots__ = ("_names",)

    def __init__(self, names: frozenset[str] = frozenset()) -> None:
        self._names = names

    def has(self, name: str) -> bool:
        """Whether the device has the Capability *name*.

        Raises:
            ValueError: if *name* is not in the Capability vocabulary, so a
                misspelt name never reads as absent hardware.
        """
        if not is_capability(name):
            raise ValueError(f"{name!r} is not a Capability")
        return name in self._names


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
        missing = describe_capabilities(capabilities)
        if scene is None:
            super().__init__(f"The device lacks {missing}")
        else:
            super().__init__(f"Scene '{scene}' needs {missing}, which the device lacks")

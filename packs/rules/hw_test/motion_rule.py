from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass

from engine.engine import GameRule, Version

_VERSION: Final = Version(1, 0)

ACCEL_MAX: Final = 9.8


class HwTestMotionRule(GameRule):
    """Stub for hardware motion (IMU) test rule — to be implemented."""

    __slots__ = ()

    def __init__(self) -> None:
        super().__init__("hw_test.motion", _VERSION)


RULE = HwTestMotionRule()

from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass

from engine.engine import GameRule, Version

_VERSION: Final = Version(1, 0)


class HwTestNetworkRule(GameRule):
    """Stub for hardware network (IR/radio) test rule — to be implemented."""

    __slots__ = ()

    def __init__(self) -> None:
        super().__init__("hw_test.network", _VERSION)


RULE = HwTestNetworkRule()

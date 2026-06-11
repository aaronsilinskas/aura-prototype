"""Shared mode plumbing for the hardware_test scene rules.

Lives in ``rules/helpers/`` (a subpackage the scene scanner skips, like
``tests/``) so it can hold cross-rule constants without being mistaken for a
rule module. Mode identity and cycling live in :mod:`phases`; this module
holds the RGB idle effect table shared by ``rgb_rule`` (entry effect and
Button A re-application).
"""

from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass

from engine.state import Scope

# Shared payload for the IR/radio send-test round trip.
HW_TEST_PAYLOAD: Final = b"hw_test"

# RGB mode idle effect table: (scope, name)
RGB_IDLE: Final = (
    (Scope.PERSONAL, "elements.water"),
    (Scope.DIRECTIONAL, "elements.fire"),
    (Scope.Global.MAIN, "elements.lightning"),
    (Scope.Global.BUFF, "elements.earth"),
    (Scope.Global.DEBUFF, "elements.ice"),
)

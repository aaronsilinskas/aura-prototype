"""Cross-rule constants for the hardware_test scene.

Lives in ``rules/helpers/`` (a subpackage the scene scanner skips, like
``tests/``) so it is not mistaken for a rule module.
"""

from __future__ import annotations

from engine.state import Scope

TYPE_CHECKING = False

if TYPE_CHECKING:
    from typing import Final

HW_TEST_PAYLOAD: Final = b"hw_test"

# The IR/radio receive flash: unlike the white idle it lights over, so it shows.
RECEIVE_FLASH_COLOR: Final = 0x00FF00

# The IR/radio idle on a device lacking that hardware, in place of the white idle.
UNAVAILABLE_COLOR: Final = 0xFF0000

RGB_IDLE: Final = (
    (Scope.PERSONAL, "elements.water"),
    (Scope.DIRECTIONAL, "elements.fire"),
    (Scope.Global.MAIN, "elements.lightning"),
    (Scope.Global.BUFF, "elements.earth"),
    (Scope.Global.DEBUFF, "elements.ice"),
)

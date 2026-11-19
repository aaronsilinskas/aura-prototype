"""Phase keys and the typed phase-machine accessor for the ``hardware_test`` scene.

Because :class:`PhaseKey` compares by identity, these module-level singletons
are the *only* tokens that match the machine's current phase; a bare string
literal or integer never will.
"""

from __future__ import annotations

from engine.phase import PhaseKey, PhaseSlot

TYPE_CHECKING = False

if TYPE_CHECKING:
    from typing import Final


MODE_RGB: Final = PhaseKey("rgb")
MODE_ACCELEROMETER: Final = PhaseKey("accelerometer")
MODE_MAGNETOMETER: Final = PhaseKey("magnetometer")
MODE_IR: Final = PhaseKey("ir")
MODE_RADIO: Final = PhaseKey("radio")
MODE_SFX: Final = PhaseKey("sfx")

# Explicit cycle order for Button-B advancement. Because PhaseKey is opaque
# (identity-only, no arithmetic), the cycle is this ordered tuple plus
# next_in_cycle, rather than `(mode + 1) % NUM_MODES`.
MODE_ORDER: Final = (
    MODE_RGB,
    MODE_ACCELEROMETER,
    MODE_MAGNETOMETER,
    MODE_IR,
    MODE_RADIO,
    MODE_SFX,
)

hw_phase: PhaseSlot = PhaseSlot("hw_phase", MODE_RGB)


def next_in_cycle(order: tuple[PhaseKey, ...], current: PhaseKey) -> PhaseKey:
    """Return the phase after *current* in *order*, wrapping to the start.

    Falls back to ``order[0]`` if *current* is not found in *order* (should
    not happen in practice since all phases in the cycle own a rule).
    """
    for index, phase in enumerate(order):
        if phase is current:
            return order[(index + 1) % len(order)]
    return order[0]

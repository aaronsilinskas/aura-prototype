"""Phase keys and the typed phase-machine accessor for the ``hardware_test`` scene.

The hardware_test scene cycles through five hardware-test modes — RGB,
Accelerometer, IR, Radio, SFX — driven by the reusable phase-machine primitive
in :mod:`engine.phase`. This module owns the scene's named :class:`PhaseKey`
instances, the single :data:`hw_phase` :class:`~engine.state.StateSlot` that
fixes the machine key and the initial phase, and the explicit :data:`MODE_ORDER`
cycle plus :func:`next_in_cycle` helper that drives Button-B advancement.

Because :class:`PhaseKey` compares by identity, these module-level singletons
are the *only* tokens that match the machine's current phase; a bare string
literal or integer never will. All five modes share the one machine cached
under :data:`HW_MACHINE_KEY`.
"""

from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass  # typing not available on all embedded runtimes

from engine.phase import PhaseKey, PhaseMachine
from engine.state import StateSlot

# ---------------------------------------------------------------------------
# Phase keys — identity-typed singletons owned by the scene
# ---------------------------------------------------------------------------

MODE_RGB: Final = PhaseKey("rgb")
MODE_ACCELEROMETER: Final = PhaseKey("accelerometer")
MODE_IR: Final = PhaseKey("ir")
MODE_RADIO: Final = PhaseKey("radio")
MODE_SFX: Final = PhaseKey("sfx")

# Explicit cycle order for Button-B advancement. Because PhaseKey is opaque
# (identity-only, no arithmetic), the cycle is this ordered tuple plus
# next_in_cycle, rather than `(mode + 1) % NUM_MODES`.
MODE_ORDER: Final = (MODE_RGB, MODE_ACCELEROMETER, MODE_IR, MODE_RADIO, MODE_SFX)

HW_MACHINE_KEY: Final = "hw_phase"

hw_phase: StateSlot = StateSlot(HW_MACHINE_KEY, lambda s: PhaseMachine(MODE_RGB), PhaseMachine)


def next_in_cycle(order: tuple[PhaseKey, ...], current: PhaseKey) -> PhaseKey:
    """Return the phase after *current* in *order*, wrapping to the start.

    Falls back to ``order[0]`` if *current* is not found in *order* (should
    not happen in practice since all phases in the cycle own a rule).
    """
    for index, phase in enumerate(order):
        if phase is current:
            return order[(index + 1) % len(order)]
    return order[0]

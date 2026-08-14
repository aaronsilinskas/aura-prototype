"""Phase keys and the typed phase-machine accessor for the ``hardware_test`` scene.

The hardware_test scene cycles through six hardware-test modes — RGB,
Accelerometer, Magnetometer, IR, Radio, SFX — driven by the reusable
phase-machine primitive in :mod:`engine.phase`. This module owns the scene's
named :class:`PhaseKey` instances, the single :data:`hw_phase`
:class:`~engine.phase.PhaseSlot` -- see that class's docstring for how every
hardware_test rule and this module-level reference come to share one
:class:`~engine.phase.PhaseMachine` -- and the explicit :data:`MODE_ORDER`
cycle plus :func:`next_in_cycle` helper that drives Button-B advancement.

Because :class:`PhaseKey` compares by identity, these module-level singletons
are the *only* tokens that match the machine's current phase; a bare string
literal or integer never will. All six modes share the one machine held by
:data:`hw_phase`.
"""

from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass  # typing not available on all embedded runtimes

from engine.phase import PhaseKey, PhaseSlot

# ---------------------------------------------------------------------------
# Phase keys — identity-typed singletons owned by the scene
# ---------------------------------------------------------------------------

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

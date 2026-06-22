"""Scene-typed phase-rule bases that bind RLGL rules to the RLGL phase machine.

The reusable :class:`PhaseRule` / :class:`InPhaseRule` primitives build a
per-instance :class:`~engine.state.StateSlot` at construction from the supplied
*machine_key* and *initial_phase*. These two thin bases pass the RLGL scene's
:data:`~packs.scenes.red_light_green_light.rules.helpers.phases.RLGL_MACHINE_KEY`
and :data:`~packs.scenes.red_light_green_light.rules.helpers.phases.PHASE_READY`,
so an RLGL rule subclass only has to name *its* phase.

Because :data:`~packs.scenes.red_light_green_light.rules.helpers.phases.rlgl_phase`
and the per-instance slot both use the same ``GameState`` key, they always
resolve the same cached :class:`~engine.phase.PhaseMachine` — no ``_machine``
override is needed.
"""

from __future__ import annotations

from engine.phase import InPhaseRule, PhaseKey, PhaseRule
from packs.scenes.red_light_green_light.rules.helpers.phases import (
    PHASE_READY,
    RLGL_MACHINE_KEY,
)


class RlglPhaseRule(PhaseRule):
    """A :class:`PhaseRule` bound to the RLGL scene's shared phase machine."""

    def __init__(self, phase: PhaseKey) -> None:
        super().__init__(phase, RLGL_MACHINE_KEY, PHASE_READY)


class RlglInPhaseRule(InPhaseRule):
    """An :class:`InPhaseRule` bound to the RLGL scene's shared phase machine."""

    def __init__(self, phase: PhaseKey) -> None:
        super().__init__(phase, RLGL_MACHINE_KEY, PHASE_READY)

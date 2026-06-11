"""Scene-typed phase-rule bases that bind RLGL rules to :func:`rlgl_phase`.

The reusable :class:`PhaseRule` / :class:`InPhaseRule` primitives reach their
machine through an overridable ``_machine`` hook (defaulting to the generic
:func:`engine.phase.phase_machine` accessor). These two thin bases point that
hook at the scene-typed :func:`rlgl_phase` accessor and fix the machine key and
initial phase, so an RLGL rule subclass only has to name *its* phase.
"""

from __future__ import annotations

from engine.phase import InPhaseRule, PhaseKey, PhaseMachine, PhaseRule
from engine.state import GameState
from packs.scenes.red_light_green_light.rules.helpers.phases import (
    PHASE_READY,
    RLGL_MACHINE_KEY,
    rlgl_phase,
)


class RlglPhaseRule(PhaseRule):
    """A :class:`PhaseRule` bound to the RLGL scene's shared phase machine."""

    def __init__(self, phase: PhaseKey) -> None:
        super().__init__(phase, RLGL_MACHINE_KEY, PHASE_READY)

    def _machine(self, state: GameState) -> PhaseMachine:
        return rlgl_phase(state)


class RlglInPhaseRule(InPhaseRule):
    """An :class:`InPhaseRule` bound to the RLGL scene's shared phase machine."""

    def __init__(self, phase: PhaseKey) -> None:
        super().__init__(phase, RLGL_MACHINE_KEY, PHASE_READY)

    def _machine(self, state: GameState) -> PhaseMachine:
        return rlgl_phase(state)

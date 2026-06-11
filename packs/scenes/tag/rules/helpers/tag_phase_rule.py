"""Scene-typed phase-rule bases that bind Tag rules to :func:`tag_phase`.

The reusable :class:`PhaseRule` / :class:`InPhaseRule` primitives reach their
machine through an overridable ``_machine`` hook (defaulting to the generic
:func:`engine.phase.phase_machine` accessor). These two thin bases point that
hook at the scene-typed :func:`tag_phase` accessor and fix the machine key and
initial phase, so a Tag rule subclass only has to name *its* phase.
"""

from __future__ import annotations

from engine.phase import InPhaseRule, PhaseKey, PhaseMachine, PhaseRule
from engine.state import GameState
from packs.scenes.tag.rules.helpers.phases import PHASE_READY, TAG_MACHINE_KEY, tag_phase


class TagPhaseRule(PhaseRule):
    """A :class:`PhaseRule` bound to the Tag scene's shared phase machine."""

    def __init__(self, phase: PhaseKey) -> None:
        super().__init__(phase, TAG_MACHINE_KEY, PHASE_READY)

    def _machine(self, state: GameState) -> PhaseMachine:
        return tag_phase(state)


class TagInPhaseRule(InPhaseRule):
    """An :class:`InPhaseRule` bound to the Tag scene's shared phase machine."""

    def __init__(self, phase: PhaseKey) -> None:
        super().__init__(phase, TAG_MACHINE_KEY, PHASE_READY)

    def _machine(self, state: GameState) -> PhaseMachine:
        return tag_phase(state)

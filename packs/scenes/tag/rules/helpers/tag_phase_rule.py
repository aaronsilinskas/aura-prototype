"""Scene-typed phase-rule bases that bind Tag rules to the Tag phase machine.

The reusable :class:`PhaseRule` / :class:`InPhaseRule` primitives build a
per-instance :class:`~engine.state.StateSlot` at construction from the supplied
*machine_key* and *initial_phase*. These two thin bases pass the Tag scene's
:data:`~packs.scenes.tag.rules.helpers.phases.TAG_MACHINE_KEY` and
:data:`~packs.scenes.tag.rules.helpers.phases.PHASE_READY`, so a Tag rule
subclass only has to name *its* phase.

Because :data:`~packs.scenes.tag.rules.helpers.phases.tag_phase` and the
per-instance slot both use the same ``GameState`` key, they always resolve the
same cached :class:`~engine.phase.PhaseMachine` — no ``_machine`` override is
needed.
"""

from __future__ import annotations

from engine.phase import InPhaseRule, PhaseKey, PhaseRule
from packs.scenes.tag.rules.helpers.phases import PHASE_READY, TAG_MACHINE_KEY


class TagPhaseRule(PhaseRule):
    """A :class:`PhaseRule` bound to the Tag scene's shared phase machine."""

    def __init__(self, phase: PhaseKey) -> None:
        super().__init__(phase, TAG_MACHINE_KEY, PHASE_READY)


class TagInPhaseRule(InPhaseRule):
    """An :class:`InPhaseRule` bound to the Tag scene's shared phase machine."""

    def __init__(self, phase: PhaseKey) -> None:
        super().__init__(phase, TAG_MACHINE_KEY, PHASE_READY)

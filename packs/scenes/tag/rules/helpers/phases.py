"""Shared phase constants for the ``tag`` scene.

Each rule reads ``TagState.phase`` (see
:mod:`packs.scenes.tag.rules.helpers.tag_state`), defaulting to
:data:`PHASE_READY` on a freshly-built :class:`TagState`, and returns early
if it is not its own phase. One-time entry side-effects are gated by
``TagState.just_entered`` / ``TagState.mark_entered()``, set atomically by
``TagState.enter(phase)`` when the *transitioning* rule advances the phase.
Rules dispatch in alphabetical registration order against one shared
``TagState`` — correctness must not depend on order.
"""

from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass  # typing not available on all embedded runtimes

# ---------------------------------------------------------------------------
# Phase constants
# ---------------------------------------------------------------------------

PHASE_READY: Final = "ready"
PHASE_STARTING: Final = "starting"
PHASE_PLAYING: Final = "playing"
PHASE_GAME_OVER: Final = "game_over"

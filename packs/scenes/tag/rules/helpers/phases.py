"""Shared phase constants and ``GameState`` keys for the ``tag`` scene.

Each rule reads ``tag_phase`` (defaulting to :data:`PHASE_READY` when unset)
and returns early if it is not its own phase. One-time entry side-effects are
gated by the shared ``tag_entered`` flag, which the *transitioning* rule
clears when it sets the next phase. Rules dispatch in alphabetical
registration order against one shared ``GameState`` — correctness must not
depend on order.
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

# ---------------------------------------------------------------------------
# GameState key names (all tag_ prefixed)
# ---------------------------------------------------------------------------

KEY_PHASE: Final = "tag_phase"
KEY_ENTERED: Final = "tag_entered"

# Config keys — readable from GameState, overridable via initial_data
KEY_STARTING_HITPOINTS: Final = "tag_starting_hitpoints"
KEY_DEAFEN_WINDOW: Final = "tag_deafen_window"
KEY_EXPECTED_TEAM: Final = "tag_expected_team"
KEY_EXPECTED_PLAYER: Final = "tag_expected_player"
KEY_WARNING_PULSE_COUNT: Final = "tag_warning_pulse_count"
KEY_WARNING_PULSE_DURATION: Final = "tag_warning_pulse_duration"

# Mutable game-state keys
KEY_HITPOINTS: Final = "tag_hitpoints"
KEY_PROGRESS_RECEIPT: Final = "tag_progress_receipt"
KEY_WARNING_RECEIPT: Final = "tag_warning_receipt"
KEY_WARNING_START: Final = "tag_warning_start"
KEY_DEAFEN_UNTIL: Final = "tag_deafen_until"

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_STARTING_HITPOINTS: Final = 10
DEFAULT_DEAFEN_WINDOW: Final = 0.1
DEFAULT_DEAFEN_UNTIL: Final = 0.0
DEFAULT_EXPECTED_TEAM: Final = 0
DEFAULT_EXPECTED_PLAYER: Final = 1
DEFAULT_WARNING_PULSE_COUNT: Final = 5
DEFAULT_WARNING_PULSE_DURATION: Final = 0.6

from __future__ import annotations

from packs.scenes.red_light_green_light.rules.helpers.phases import (
    PHASE_GREEN,
    PHASE_GREEN_WARNING,
)
from packs.scenes.red_light_green_light.rules.helpers.warning_rule import RlglWarningRule

RULE = RlglWarningRule(PHASE_GREEN_WARNING, PHASE_GREEN)

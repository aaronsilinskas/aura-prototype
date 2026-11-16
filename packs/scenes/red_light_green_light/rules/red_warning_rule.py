"""RLGL scene Red Warning phase rule: the warning sting, then Red.

See :mod:`~packs.scenes.red_light_green_light.rules.helpers.warning_rule`,
which this phase shares with Green Warning.
"""

from __future__ import annotations

from packs.scenes.red_light_green_light.rules.helpers.phases import PHASE_RED, PHASE_RED_WARNING
from packs.scenes.red_light_green_light.rules.helpers.warning_rule import RlglWarningRule

RULE = RlglWarningRule(PHASE_RED_WARNING, PHASE_RED)

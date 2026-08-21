"""``ir_range_meter`` -- the per-scene ``ReceptionQualityMeter`` accessor.

Kept separate from ``reception_quality_meter.py`` so that module stays a pure,
``GameState``-free classifier. Builds the meter once from the scene's cached
:class:`IrRangeConfig` and caches the instance under a single ``GameState``
key, mirroring the ``rlgl_config``/``tag_config`` accessor precedent.
"""

from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass

from engine.state import GameState, StateSlot
from packs.scenes.ir_range_receiver.rules.helpers.ir_range_config import ir_range_config
from packs.scenes.ir_range_receiver.rules.helpers.reception_quality_meter import (
    ReceptionQualityMeter,
)

_METER_KEY: Final = "ir_range_meter"


def _build_meter(state: GameState) -> ReceptionQualityMeter:
    config = ir_range_config(state)
    return ReceptionQualityMeter(
        window_seconds=config.window_seconds,
        silence_timeout=config.silence_timeout,
        green_threshold=config.green_threshold,
    )


ir_range_meter: StateSlot = StateSlot(_METER_KEY, _build_meter, ReceptionQualityMeter)

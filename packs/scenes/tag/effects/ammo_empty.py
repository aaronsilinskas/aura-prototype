"""Tag scene "ammo_empty" effect — looping red pulse shown while ammo is empty.

Its options override anything a caller passes, so the look is consistent
wherever the ammo bar goes empty. With no ``stops_effect`` audio it runs until
``Global.BUFF`` is replaced (by ``scene.reload`` or a fresh ammo bar) or torn down.
"""

from engine.effects.builder import ComposedEffectBuilder
from packs.effects.basic.pulse import PulseBuilder

BUILD = ComposedEffectBuilder(
    PulseBuilder(),
    options={
        "start_color": 0x000000,
        "end_color": 0xFF0000,
        "brighten_duration": 0.6,
        "on_duration": 0.0,
        "darken_duration": 0.6,
        "off_duration": 0.0,
    },
)

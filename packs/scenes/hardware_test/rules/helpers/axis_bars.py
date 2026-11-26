"""Three progress bars, one per axis of a 3-axis sensor reading."""

from __future__ import annotations

from engine.state import Scope

TYPE_CHECKING = False

if TYPE_CHECKING:
    from typing import Final

    from engine.input import AccelerationData, MagneticData
    from engine.state import EffectControls

# Each axis: its reading field, the strip that shows it, and its bar color
# for a positive and a negative reading.
_AXES: Final = (
    ("x", Scope.PERSONAL, 0xFF0000, 0x00FFFF),
    ("y", Scope.DIRECTIONAL, 0x00FF00, 0xFF00FF),
    ("z", Scope.Global.ALL, 0x0000FF, 0xFFFF00),
)


def start_axis_bars(effect_controls: EffectControls) -> None:
    for _field, scope, pos_color, _neg_color in _AXES:
        effect_controls.set_effect(scope, "basic.progress", {"color": pos_color, "progress": 0.0})


def show_axis_bars(
    effect_controls: EffectControls, reading: AccelerationData | MagneticData, full_scale: float
) -> None:
    """Fill each axis's bar by its share of ``full_scale``, colored by the reading's sign."""
    for field, scope, pos_color, neg_color in _AXES:
        value = getattr(reading, field)
        color = pos_color if value >= 0 else neg_color
        progress = min(1.0, abs(value) / full_scale)
        effect_controls.set_effect(scope, "basic.progress", {"color": color, "progress": progress})

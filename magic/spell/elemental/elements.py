from __future__ import annotations

TYPE_CHECKING = False

if TYPE_CHECKING:
    from typing import Final


class ElementTags:
    """String constants for the elemental affinities a spell can carry."""

    FIRE: Final = "element.fire"
    WATER: Final = "element.water"
    EARTH: Final = "element.earth"
    ICE: Final = "element.ice"
    AIR: Final = "element.air"
    LIGHTNING: Final = "element.lightning"
    LIGHT: Final = "element.light"
    DARK: Final = "element.dark"
    TIME: Final = "element.time"
    GRAVITY: Final = "element.gravity"

from __future__ import annotations

from magic.aura import Spell

TYPE_CHECKING = False

if TYPE_CHECKING:
    from typing import Final


class CastType:
    LINE: Final = "line"
    CONE: Final = "cone"
    AREA_OF_EFFECT: Final = "aoe"


class Caster:
    """Interface for casting spells from a source such as a player or NPC."""

    def cast_spell(self, spell: Spell, cast_type: str) -> None:
        raise NotImplementedError("cast_spell must be implemented by subclasses.")

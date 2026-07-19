try:
    from typing import Final
except ImportError:
    pass

from magic.aura import Spell


class CastType:
    """Enumeration of cast types."""

    LINE: Final = "line"
    CONE: Final = "cone"
    AREA_OF_EFFECT: Final = "aoe"


class Caster:
    """Interface for casting spells from a source such as a player or NPC."""

    def cast_spell(self, spell: Spell, cast_type: str) -> None:
        """Casts a spell."""
        raise NotImplementedError("cast_spell must be implemented by subclasses.")

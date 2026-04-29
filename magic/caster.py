from magic.aura import Spell


class CastType:
    """Enumeration of cast types."""

    LINE = "line"
    CONE = "cone"
    AREA_OF_EFFECT = "aoe"


class Caster:

    def cast_spell(self, spell: Spell, cast_type: str) -> None:
        """Casts a spell."""
        raise NotImplementedError("cast_spell must be implemented by subclasses.")

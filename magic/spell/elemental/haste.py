from magic.aura import Aura, Spell, SpellTags
from magic.spell.elemental.elements import ElementTags
from magic.values import Duration, ValueModifier


class HasteSpell(Spell):
    """Decreases the delay between spell casts for a duration by a percentage.

    Level scaling: Decreases the cast delay.
    """

    def __init__(self, duration: float, cast_delay_percentage: float) -> None:
        super().__init__([SpellTags.BUFF, ElementTags.AIR])
        self.duration = Duration(duration)
        self._base_cast_delay_percentage = max(min(cast_delay_percentage, 1.0), 0.0)
        self.cast_delay_percentage = self._base_cast_delay_percentage
        self._modifier = ValueModifier(
            1 - self.cast_delay_percentage, duration=self.duration.length
        )

    def start(self, aura: Aura) -> None:
        aura.cast_delay.modifiers.add(self._modifier)

    def update(self, aura: Aura, elapsed_time: float) -> bool:
        return self.duration.update(elapsed_time)

    def stop(self, aura: Aura) -> None:
        aura.cast_delay.modifiers.remove(self._modifier)

    def on_level_changed(self, level: int) -> None:
        self.cast_delay_percentage = Spell.LEVEL_SCALER.scale_value(
            self._base_cast_delay_percentage, level
        )
        self._modifier.multiplier = 1 - self.cast_delay_percentage

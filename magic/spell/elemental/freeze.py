from magic.aura import Aura, Spell, SpellTags
from magic.spell.elemental.elements import ElementTags
from magic.values import Duration, ValueModifier


class FreezeSpell(Spell):
    """Increases the delay between spell casts for a duration.

    Level scaling: Increases the cast delay multiplier.
    """

    def __init__(self, duration: float, cast_delay_modifier: float) -> None:
        super().__init__([SpellTags.DEBUFF, ElementTags.ICE])
        self.duration = Duration(duration)
        self._base_cast_delay_modifier = max(cast_delay_modifier, 1.0)
        self.cast_delay_modifier = self._base_cast_delay_modifier
        self._modifier = ValueModifier(self.cast_delay_modifier, duration=self.duration.length)

    def start(self, aura: Aura) -> None:
        aura.cast_delay.modifiers.add(self._modifier)

    def update(self, aura: Aura, elapsed_time: float) -> bool:
        return self.duration.update(elapsed_time)

    def stop(self, aura: Aura) -> None:
        aura.cast_delay.modifiers.remove(self._modifier)

    def on_level_changed(self, level: int) -> None:
        self.cast_delay_modifier = Spell.LEVEL_SCALER.scale_value(
            self._base_cast_delay_modifier, level
        )
        self._modifier.multiplier = self.cast_delay_modifier

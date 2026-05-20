from magic.aura import Aura, DamageEvent, Spell, SpellTags
from magic.spell.elemental.elements import ElementTags
from magic.values import Duration


class IgniteSpell(Spell):
    """Damage over time spell that deals damage per second for a duration.

    Level scaling: Increases the damage per second.
    """

    def __init__(self, damage_per_second: float, duration: float) -> None:
        super().__init__([SpellTags.DEBUFF, ElementTags.FIRE])
        self.duration = Duration(duration)
        self._base_damage_per_second = damage_per_second
        self.damage_per_second = damage_per_second

    def update(self, aura: Aura, elapsed_time: float) -> bool:
        damage = self.damage_per_second * min(elapsed_time, self.duration.remaining)
        aura.process_event(DamageEvent(damage))

        return self.duration.update(elapsed_time)

    def on_level_changed(self, level: int) -> None:
        self.damage_per_second = Spell.LEVEL_SCALER.scale_value(self._base_damage_per_second, level)

from magic.aura import Aura, AuraEvent, DamageEvent, Spell, SpellTags
from magic.spell.elemental.elements import ElementTags
from magic.values import Duration


class VulnerableSpell(Spell):
    """Removes any existing or new shields while this spell is active.
    If no shields are removed, increases damage taken for a duration.

    Level scaling: Increases the damage multiplier.
    """

    def __init__(self, damage_multiplier: float, duration: float) -> None:
        super().__init__([SpellTags.DEBUFF, ElementTags.DARK])
        self.duration = Duration(duration)
        self._base_damage_multiplier: float = max(1.0, damage_multiplier)
        self.damage_multiplier: float = self._base_damage_multiplier
        self.shield_spells_removed: bool = False

    def update(self, aura: Aura, elapsed_time: float) -> bool:
        shield_spells = aura.spells.get_by_tag(SpellTags.SHIELD)
        for spell in shield_spells:
            aura.remove_spell(spell)

        if len(shield_spells) > 0:
            self.shield_spells_removed = True

        return self.duration.update(elapsed_time)

    def modify_event(self, aura: Aura, event: AuraEvent) -> None:
        if not self.shield_spells_removed and isinstance(event, DamageEvent):
            event.amount *= self.damage_multiplier

    def _update_level(self, level: int) -> None:
        self.damage_multiplier = Spell.LEVEL_SCALER.scale_value(self._base_damage_multiplier, level)
        self.damage_multiplier = max(1.0, self.damage_multiplier)

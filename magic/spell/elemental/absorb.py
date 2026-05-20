from magic.aura import AddSpellEvent, Aura, AuraEvent, Spell, SpellTags
from magic.spell.elemental.elements import ElementTags
from magic.values import Duration


class AbsorbSpell(Spell):
    """A spell that absorbs debuff spells, and expires after a duration. The number of
    debuff spells it can absorb increases with level.

    Level scaling: Increases the number of debuff spells that can be absorbed.
    """

    def __init__(self, duration: float) -> None:
        super().__init__([SpellTags.BUFF, ElementTags.GRAVITY])
        self.duration = Duration(duration)
        self._absorb_count = 1

    def update(self, aura: Aura, elapsed_time: float) -> bool:
        if self._absorb_count <= 0:
            return True

        return self.duration.update(elapsed_time)

    def _update_level(self, level: int) -> None:
        self._absorb_count = round(Spell.LEVEL_SCALER.scale_value(1, level))

    def modify_event(self, aura: Aura, event: AuraEvent) -> None:
        if self._absorb_count <= 0:
            return

        if isinstance(event, AddSpellEvent):
            spell = event.spell
            if SpellTags.DEBUFF in spell.tags:
                event.is_canceled = True
                self._absorb_count -= 1

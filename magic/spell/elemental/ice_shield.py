from magic.aura import Aura, AuraEvent, DamageEvent, Spell, SpellTags
from magic.caster import Caster, CastType
from magic.spell.elemental.elements import ElementTags
from magic.spell.elemental.freeze import FreezeSpell
from magic.values import Counter, Duration


class IceShieldSpell(Spell):
    """Resists incoming damage for a number of hits or duration. Casts Freeze in an AOE
    when max hits is reached.
    """

    def __init__(
        self,
        reduction: float,
        max_hits: int,
        duration: float,
        freeze_spell: FreezeSpell,
        caster: Caster,
    ) -> None:
        super().__init__([SpellTags.BUFF, SpellTags.SHIELD, ElementTags.ICE])

        self.duration = Duration(duration)
        self._base_reduction = max(0, min(reduction, 1))
        self.reduction = max(0, min(reduction, 1))
        self.hits = Counter(max=max_hits)
        self._freeze_spell = freeze_spell
        self._caster = caster

    def update(self, aura: Aura, elapsed_time: float) -> bool:
        return self.duration.update(elapsed_time)

    @property
    def is_spent(self) -> bool:
        return self.hits.is_max

    def modify_event(self, aura: Aura, event: AuraEvent) -> None:
        if self.duration.is_expired or self.hits.is_max:
            return

        if isinstance(event, DamageEvent):
            event.amount *= 1 - self.reduction
            self.hits.increment()
            if self.hits.is_max:
                self._caster.cast_spell(
                    self._freeze_spell, cast_type=CastType.AREA_OF_EFFECT
                )  # Cast type can be arbitrary here

    def on_level_changed(self, level: int) -> None:
        self.reduction = Spell.LEVEL_SCALER.scale_percentage(self._base_reduction, level)

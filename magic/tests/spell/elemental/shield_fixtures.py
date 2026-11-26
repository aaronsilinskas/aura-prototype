import random

from magic.spell.elemental.earth_shield import EarthShieldSpell
from magic.spell.elemental.freeze import FreezeSpell
from magic.spell.elemental.ice_shield import IceShieldSpell
from magic.spell.elemental.slice import SliceSpell
from magic.tests.helpers import AuraFixture, MockCaster


class _ShieldFixture(AuraFixture):
    """A shield's random hit and time limits, and a hit of ``1 / hits_to_drain`` of max magic."""

    def __init__(self, damage_reduction: float, hits_to_drain: int) -> None:
        super().__init__()
        self.damage_reduction = damage_reduction
        self.max_hits = random.randint(3, 5)
        self.duration = round(random.uniform(5.0, 10.0))
        self.damage = self.aura.magic.max.value / hits_to_drain
        self.damage_spell = SliceSpell(damage=self.damage)
        self.damage_after_shield = self.damage * (1 - self.damage_reduction)


class EarthShieldFixture(_ShieldFixture):
    def __init__(self) -> None:
        super().__init__(damage_reduction=0.75, hits_to_drain=2)
        self.shield_spell = EarthShieldSpell(
            reduction=self.damage_reduction,
            max_hits=self.max_hits,
            duration=self.duration,
        )


class IceShieldFixture(_ShieldFixture):
    def __init__(self) -> None:
        super().__init__(damage_reduction=0.50, hits_to_drain=4)
        self.caster = MockCaster()
        self.freeze_spell = FreezeSpell(duration=5.0, cast_delay_modifier=2.0)
        self.shield_spell = IceShieldSpell(
            reduction=self.damage_reduction,
            max_hits=self.max_hits,
            duration=self.duration,
            freeze_spell=self.freeze_spell,
            caster=self.caster,
        )

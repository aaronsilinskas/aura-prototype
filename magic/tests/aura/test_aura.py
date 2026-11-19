import pytest

from magic.aura import (
    Aura,
    AuraEvent,
    DamageEvent,
    HealEvent,
    RemoveSpellEvent,
    Spell,
    SpellTags,
)
from magic.tests.helpers import AuraFixture, MockEventListener, NoopSpell
from magic.values import ValueModifier


@pytest.fixture
def fixture() -> AuraFixture:
    return AuraFixture()


def test_aura_initialization(fixture: AuraFixture) -> None:
    aura = fixture.aura
    assert aura.magic.value == fixture.max_magic
    assert aura.magic.max.value == fixture.max_magic
    assert len(aura.spells) == 0


def test_damage_past_the_minimum_leaves_magic_at_the_minimum(fixture: AuraFixture) -> None:
    aura = fixture.aura
    damage_past_min = aura.magic.value - aura.magic.min + 50.0

    aura.process_event(DamageEvent(damage_past_min))

    assert aura.magic.value == aura.magic.min


def test_healing_past_the_maximum_leaves_magic_at_the_maximum(fixture: AuraFixture) -> None:
    aura = fixture.aura
    heal_past_max = aura.magic.max.value * 10

    aura.process_event(HealEvent(heal_past_max))

    assert aura.magic.value == aura.magic.max.value


def test_update_triggers_magic_value_update(fixture: AuraFixture) -> None:
    aura = fixture.aura
    modifier = ValueModifier(1.0, duration=0.1)
    aura.magic.max.modifiers.add(modifier)

    aura.update(1.0)

    assert len(aura.magic.max.modifiers) == 0


def test_update_triggers_cast_delay_update(fixture: AuraFixture) -> None:
    aura = fixture.aura
    modifier = ValueModifier(0.5, duration=0.1)
    aura.cast_delay.modifiers.add(modifier)

    aura.update(1.0)

    assert len(aura.cast_delay.modifiers) == 0


class SpentByOneHitSpell(NoopSpell):
    def __init__(self) -> None:
        super().__init__(tags=[])
        self.hit = False

    @property
    def is_spent(self) -> bool:
        return self.hit

    def modify_event(self, aura: Aura, event: AuraEvent) -> None:
        if isinstance(event, DamageEvent):
            self.hit = True


class HitEveryUpdateSpell(NoopSpell):
    def __init__(self) -> None:
        super().__init__(tags=[])

    def update(self, aura: Aura, elapsed_time: float) -> bool:
        aura.process_event(DamageEvent(1.0))
        return False


@pytest.mark.parametrize("spent_first", [True, False], ids=["spent_first", "hitter_first"])
def test_a_spell_spent_by_another_spells_update_leaves_in_that_same_update(
    fixture: AuraFixture, spent_first: bool
) -> None:
    aura = fixture.aura
    spent = SpentByOneHitSpell()
    hitter = HitEveryUpdateSpell()
    for spell in [spent, hitter] if spent_first else [hitter, spent]:
        aura.add_spell(spell)

    aura.update(0.1)

    assert list(aura.spells) == [hitter]


def test_listeners_hear_a_spent_spell_removed_in_the_update_that_spent_it(
    fixture: AuraFixture,
) -> None:
    aura = fixture.aura
    listener = MockEventListener()
    aura.event_listeners.append(listener)
    spent = SpentByOneHitSpell()
    aura.add_spell(spent)
    aura.add_spell(HitEveryUpdateSpell())

    aura.update(0.1)

    removed = [e.spell for _, e in listener.events if isinstance(e, RemoveSpellEvent)]
    assert removed == [spent]


def test_update_runs_each_spells_update_once_even_when_a_spell_is_spent(
    fixture: AuraFixture,
) -> None:
    aura = fixture.aura

    class CountingSpell(NoopSpell):
        def __init__(self) -> None:
            super().__init__(tags=[])
            self.updates = 0

        def update(self, aura: Aura, elapsed_time: float) -> bool:
            self.updates += 1
            return False

    counting = CountingSpell()
    aura.add_spell(counting)
    aura.add_spell(SpentByOneHitSpell())
    aura.add_spell(HitEveryUpdateSpell())

    aura.update(0.1)

    assert counting.updates == 1


def test_handle_event_applies_damage_event(fixture: AuraFixture) -> None:
    aura = fixture.aura
    initial_magic = aura.magic.value
    damage_amount = 150.0

    aura.process_event(DamageEvent(damage_amount))

    assert aura.magic.value == initial_magic - damage_amount


def test_handle_event_applies_heal_event(fixture: AuraFixture) -> None:
    aura = fixture.aura
    aura.magic.value = fixture.max_magic / 2
    initial_magic = aura.magic.value
    heal_amount = fixture.max_magic / 4

    aura.process_event(HealEvent(heal_amount))

    assert aura.magic.value == initial_magic + heal_amount


def test_handle_event_cancellation(fixture: AuraFixture) -> None:
    aura = fixture.aura
    initial_magic = aura.magic.value
    damage_amount = 200.0

    class CancelingSpell(Spell):
        def __init__(self) -> None:
            super().__init__(tags=[])

        def modify_event(self, aura: Aura, event: AuraEvent) -> None:
            event.is_canceled = True

    aura.add_spell(CancelingSpell())

    aura.process_event(DamageEvent(damage_amount))

    assert aura.magic.value == initial_magic


def test_get_by_name_returns_every_spell_with_that_name(fixture: AuraFixture) -> None:
    aura = fixture.aura

    class InexorableDoomSpell(Spell):
        def __init__(self) -> None:
            super().__init__(tags=[])

    class AnotherSpell(Spell):
        def __init__(self) -> None:
            super().__init__(tags=[])

    test_spell = InexorableDoomSpell()
    test_spell_2 = InexorableDoomSpell()
    aura.add_spell(test_spell)
    aura.add_spell(test_spell_2)
    aura.add_spell(AnotherSpell())

    spells_by_name = list(aura.spells.get_by_name(test_spell.name))

    assert spells_by_name == [test_spell, test_spell_2]


def test_get_spells_by_tag(fixture: AuraFixture) -> None:
    aura = fixture.aura

    class BuffSpell(Spell):
        def __init__(self) -> None:
            super().__init__(tags=[SpellTags.BUFF])

    class DebuffSpell(Spell):
        def __init__(self) -> None:
            super().__init__(tags=[SpellTags.DEBUFF])

    buff_spell = BuffSpell()
    debuff_spell = DebuffSpell()

    aura.add_spell(buff_spell)
    aura.add_spell(debuff_spell)

    buff_spells = list(aura.spells.get_by_tag(SpellTags.BUFF))
    debuff_spells = list(aura.spells.get_by_tag(SpellTags.DEBUFF))

    assert buff_spell in buff_spells
    assert debuff_spell in debuff_spells


def test_get_spells_by_multiple_tags(fixture: AuraFixture) -> None:
    aura = fixture.aura

    class ShieldSpell(Spell):
        def __init__(self) -> None:
            super().__init__(tags=[SpellTags.SHIELD])

    class ShieldBuffSpell(Spell):
        def __init__(self) -> None:
            super().__init__(tags=[SpellTags.SHIELD, SpellTags.BUFF])

    class BuffSpell(Spell):
        def __init__(self) -> None:
            super().__init__(tags=[SpellTags.BUFF])

    shield_spell = ShieldSpell()
    shield_buff_spell = ShieldBuffSpell()
    buff_spell = BuffSpell()

    aura.add_spell(shield_spell)
    aura.add_spell(shield_buff_spell)
    aura.add_spell(buff_spell)

    shield_buff_spells = list(aura.spells.get_by_tag(SpellTags.SHIELD, SpellTags.BUFF))
    assert shield_buff_spells == [shield_buff_spell]

    shield_spells = list(aura.spells.get_by_tag(SpellTags.SHIELD))
    assert set(shield_spells) == {shield_spell, shield_buff_spell}

    buff_spells = list(aura.spells.get_by_tag(SpellTags.BUFF))
    assert set(buff_spells) == {shield_buff_spell, buff_spell}


def test_get_spells_by_tag_empty(fixture: AuraFixture) -> None:
    aura = fixture.aura

    class BuffSpell(Spell):
        def __init__(self) -> None:
            super().__init__(tags=[SpellTags.BUFF])

    aura.add_spell(BuffSpell())

    spells = list(aura.spells.get_by_tag())
    assert spells == [], "asking for no tags matches nothing"

    spells = list(aura.spells.get_by_tag(SpellTags.DEBUFF))
    assert spells == [], "a tag no spell carries matches no spell"


def test_get_spells_by_class(fixture: AuraFixture) -> None:
    aura = fixture.aura

    class CustomSpellA(Spell):
        def __init__(self) -> None:
            super().__init__(tags=[])

    class CustomSpellB(Spell):
        def __init__(self) -> None:
            super().__init__(tags=[])

    spell_a1 = CustomSpellA()
    spell_a2 = CustomSpellA()
    spell_b = CustomSpellB()

    aura.add_spell(spell_a1)
    aura.add_spell(spell_a2)
    aura.add_spell(spell_b)

    spells_a = list(aura.spells.get_by_class(CustomSpellA))
    spells_b = list(aura.spells.get_by_class(CustomSpellB))

    assert spells_a == [spell_a1, spell_a2]
    assert spells_b == [spell_b]

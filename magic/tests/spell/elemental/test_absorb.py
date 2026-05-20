import pytest

from magic.aura import Spell, SpellTags
from magic.spell.elemental.absorb import AbsorbSpell
from magic.tests.helpers import AuraFixture, NoopSpell


class DebuffSpell(NoopSpell):
    def __init__(self) -> None:
        super().__init__(tags=[SpellTags.DEBUFF])


class BuffSpell(NoopSpell):
    def __init__(self) -> None:
        super().__init__(tags=[SpellTags.BUFF])


class AbsorbFixture(AuraFixture):
    def __init__(self) -> None:
        super().__init__()
        self.duration = 10.0
        self.absorb_spell = AbsorbSpell(duration=self.duration)


@pytest.fixture
def fixture() -> AbsorbFixture:
    return AbsorbFixture()


def test_absorb_removes_single_debuff_on_add(fixture: AbsorbFixture) -> None:
    aura = fixture.aura

    # Add absorb spell
    aura.add_spell(fixture.absorb_spell)

    # Add a debuff spell - should be absorbed
    debuff = DebuffSpell()
    aura.add_spell(debuff)
    aura.update(0.1)

    # Debuff should be prevented from being added, absorb count is now 0
    # Absorb should remove itself when count reaches 0
    assert debuff not in list(aura.spells)
    assert fixture.absorb_spell not in list(aura.spells)


def test_absorb_removes_itself_after_absorb_count_depleted(
    fixture: AbsorbFixture,
) -> None:
    aura = fixture.aura

    # Add absorb spell (level 1 = 1 absorb)
    aura.add_spell(fixture.absorb_spell)

    # Add first debuff - should be absorbed
    debuff1 = DebuffSpell()
    aura.add_spell(debuff1)
    aura.update(0.1)

    # Absorb count is 0, spell should remove itself
    assert fixture.absorb_spell not in list(aura.spells)

    # Add second debuff - absorb is gone, should not absorb
    debuff2 = DebuffSpell()
    aura.add_spell(debuff2)
    aura.update(0.1)

    # Second debuff should remain (not absorbed)
    assert debuff2 in list(aura.spells)


def test_absorb_expires_after_duration(fixture: AbsorbFixture) -> None:
    aura = fixture.aura

    # Add absorb spell
    aura.add_spell(fixture.absorb_spell)

    # Update past duration
    aura.update(fixture.duration + 1.0)

    # Absorb should be removed
    assert fixture.absorb_spell not in list(aura.spells)


def test_absorb_does_not_remove_buffs(fixture: AbsorbFixture) -> None:
    aura = fixture.aura

    # Add absorb spell
    aura.add_spell(fixture.absorb_spell)

    # Add a buff spell - should not be absorbed
    buff = BuffSpell()
    aura.add_spell(buff)
    aura.update(0.1)

    # Buff should remain
    assert buff in list(aura.spells)
    assert fixture.absorb_spell in list(aura.spells)


def test_absorb_level_scaling(fixture: AbsorbFixture) -> None:
    aura = fixture.aura

    # Create level 3 absorb spell
    absorb_level_3 = AbsorbSpell(duration=10.0)
    absorb_level_3.level = 3
    aura.add_spell(absorb_level_3)

    # Calculate expected absorb count: round(1 * (1 + 0.25 * (3 - 1))) = round(1.5) = 2
    expected_count = round(Spell.LEVEL_SCALER.scale_value(1, 3))
    assert expected_count == 2

    # Add first debuff - should be absorbed
    debuff1 = DebuffSpell()
    aura.add_spell(debuff1)
    aura.update(0.1)

    assert debuff1 not in list(aura.spells)
    assert absorb_level_3 in list(aura.spells)  # Still has 1 absorb left

    # Add second debuff - should be absorbed
    debuff2 = DebuffSpell()
    aura.add_spell(debuff2)
    aura.update(0.1)

    assert debuff2 not in list(aura.spells)
    # Count is now 0, absorb should remove itself
    assert absorb_level_3 not in list(aura.spells)

    # Add third debuff - absorb is gone, should not absorb
    debuff3 = DebuffSpell()
    aura.add_spell(debuff3)
    aura.update(0.1)

    assert debuff3 in list(aura.spells)


def test_absorb_higher_level_scaling(fixture: AbsorbFixture) -> None:
    aura = fixture.aura

    # Create level 5 absorb spell
    absorb_level_5 = AbsorbSpell(duration=10.0)
    absorb_level_5.level = 10
    aura.add_spell(absorb_level_5)

    # Calculate expected absorb count: round(1 * (1 + 0.25 * (10 - 1))) = round(3.25) = 3
    expected_count = round(Spell.LEVEL_SCALER.scale_value(1, 10))
    assert expected_count == 3

    # Absorb 3 debuffs
    for _ in range(expected_count):
        debuff = DebuffSpell()
        aura.add_spell(debuff)
        aura.update(0.1)
        assert debuff not in list(aura.spells)

    # Fourth debuff should not be absorbed
    debuff = DebuffSpell()
    aura.add_spell(debuff)
    aura.update(0.1)
    assert debuff in list(aura.spells)


def test_absorb_multiple_debuffs_simultaneously(fixture: AbsorbFixture) -> None:
    aura = fixture.aura

    # Create level 3 absorb to handle multiple debuffs
    absorb = AbsorbSpell(duration=10.0)
    absorb.level = 3
    aura.add_spell(absorb)

    # Add two debuffs
    debuff1 = DebuffSpell()
    debuff2 = DebuffSpell()
    aura.add_spell(debuff1)
    aura.add_spell(debuff2)
    aura.update(0.1)

    # Both should be absorbed, absorb still has capacity
    assert debuff1 not in list(aura.spells)
    assert debuff2 not in list(aura.spells)
    # Absorb should still be active (count was 2, absorbed 2, so count is 0 after this update)
    assert absorb not in list(aura.spells)


def test_absorb_does_not_absorb_after_depleted(fixture: AbsorbFixture) -> None:
    aura = fixture.aura

    # Add level 1 absorb (1 absorb count)
    aura.add_spell(fixture.absorb_spell)

    # Absorb one debuff
    debuff1 = DebuffSpell()
    aura.add_spell(debuff1)
    aura.update(0.1)

    # Absorb count is now 0, spell removes itself
    assert fixture.absorb_spell not in list(aura.spells)

    # Add another debuff - should not be absorbed (absorb is gone)
    debuff2 = DebuffSpell()
    aura.add_spell(debuff2)
    aura.update(0.1)

    assert debuff2 in list(aura.spells)


def test_absorb_removes_itself_when_count_zero(fixture: AbsorbFixture) -> None:
    aura = fixture.aura

    # Add level 1 absorb (1 absorb count)
    aura.add_spell(fixture.absorb_spell)

    # Absorb one debuff
    debuff = DebuffSpell()
    aura.add_spell(debuff)
    aura.update(0.1)

    # Absorb count is now 0, next update should remove it
    aura.update(0.1)

    assert fixture.absorb_spell not in list(aura.spells)

import pytest

from magic.aura import Spell
from magic.spell.elemental.shadow import ShadowSpell
from magic.tests.helpers import AuraFixture


class ShadowFixture(AuraFixture):
    def __init__(self) -> None:
        super().__init__()
        self.shadow_duration: float = 3.0  # seconds
        self.shadow_spell: ShadowSpell = ShadowSpell(duration=self.shadow_duration)


@pytest.fixture
def fixture() -> ShadowFixture:
    return ShadowFixture()


def test_shadow_spell_is_active_during_duration(fixture: ShadowFixture) -> None:
    aura = fixture.aura

    aura.add_spell(fixture.shadow_spell)
    aura.update(1.0)  # Update partway through duration

    # Shadow spell should still be active
    assert fixture.shadow_spell in aura.spells


def test_shadow_spell_expires_after_duration(fixture: ShadowFixture) -> None:
    aura = fixture.aura

    aura.add_spell(fixture.shadow_spell)

    # Simulate time passing until the spell expires
    aura.update(fixture.shadow_duration + 1.0)

    # The shadow spell should be expired and removed
    assert fixture.shadow_spell not in aura.spells


def test_shadow_level_scales_duration(fixture: ShadowFixture) -> None:
    level = 2
    original_duration = fixture.shadow_duration

    fixture.shadow_spell.level = level

    expected_duration = Spell.LEVEL_SCALER.scale_value(original_duration, level)
    assert fixture.shadow_spell.duration.length == expected_duration

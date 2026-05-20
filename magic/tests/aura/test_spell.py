import random

import pytest

from magic.aura import Aura, Spell
from magic.tests.helpers import AuraFixture


@pytest.fixture
def fixture() -> AuraFixture:
    return AuraFixture()


def test_spell_name_normalization(fixture: AuraFixture) -> None:
    class SuperGiantSpell(Spell):
        pass

    assert SuperGiantSpell(tags=[]).name == "SuperGiant"


class LifecycleTrackingSpell(Spell):
    """Tracks spell updates for testing purposes."""

    def __init__(self) -> None:
        super().__init__(tags=[])
        self.started = False
        self.update_elapsed_time = None
        self.stopped = False

    def start(self, aura: Aura) -> None:
        super().start(aura)
        self.started = True

    def update(self, aura: Aura, elapsed_time: float) -> bool:
        self.update_elapsed_time = elapsed_time
        return False

    def stop(self, aura: Aura) -> None:
        super().stop(aura)
        self.stopped = True


def test_add_spell_calls_start(fixture: AuraFixture) -> None:
    aura = fixture.aura
    test_spell = LifecycleTrackingSpell()

    assert test_spell.started is False

    aura.add_spell(test_spell)

    assert test_spell.started is True


def test_update_calls_spell_update(fixture: AuraFixture) -> None:
    aura = fixture.aura
    test_spell = LifecycleTrackingSpell()
    elapsed_time = random.uniform(0.5, 2.0)

    aura.add_spell(test_spell)

    assert test_spell.update_elapsed_time is None

    aura.update(elapsed_time)

    assert test_spell.update_elapsed_time == elapsed_time


def test_remove_spell_calls_stop(fixture: AuraFixture) -> None:
    aura = fixture.aura
    test_spell = LifecycleTrackingSpell()

    aura.add_spell(test_spell)

    assert test_spell.stopped is False

    aura.remove_spell(test_spell)

    assert test_spell.stopped is True

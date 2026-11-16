"""Detects sets of spells on an Aura and replaces them with a combined spell."""

from __future__ import annotations

from magic.aura import AddSpellEvent, Aura, AuraEvent, EventListener

TYPE_CHECKING = False

if TYPE_CHECKING:
    from collections.abc import Iterator


class SpellCombination:
    """Looks for a specific set of spells on an Aura and replaces them with a
    new combined spell if found."""

    def check(self, aura: Aura) -> bool:
        """Applies the combination if its spells are present, returning whether it fired."""
        raise NotImplementedError("This method should be implemented by subclasses.")


class SpellCombinations(EventListener):
    """Checks its registered combinations whenever a spell is added to the Aura."""

    def __init__(self) -> None:
        self._combinations: list[SpellCombination] = []

    def on_spell_event(self, aura: Aura, event: AuraEvent) -> None:
        """Runs every registered combination check when a spell is added."""
        if isinstance(event, AddSpellEvent):
            for combo in self._combinations:
                combo.check(aura)

    def add(self, combination: SpellCombination) -> None:
        """Registers ``combination``."""
        self._combinations.append(combination)

    def remove(self, combination: SpellCombination) -> None:
        """Unregisters ``combination`` if present."""
        if combination in self._combinations:
            self._combinations.remove(combination)

    def __len__(self) -> int:
        return len(self._combinations)

    def __iter__(self) -> Iterator[SpellCombination]:
        return iter(self._combinations)

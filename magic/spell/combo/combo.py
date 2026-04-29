"""Spell combination system for detecting and replacing spell combinations in an Aura.

This module provides the framework for creating spell combinations that can detect
specific sets of spells on an Aura and replace them with combined spells.
"""

from magic.aura import AddSpellEvent, Aura, AuraEvent, EventListener


class SpellCombination:
    """Base class for spell combinations.

    Looks for a specific set of spells on an Aura and replaces them with a new
    combined spell if found. Subclasses should implement the check method to define
    their specific combination logic.
    """

    def check(self, aura: Aura) -> bool:
        """Check if the spell combination exists on the aura and apply it if found.

        Args:
            aura: The Aura instance to check for spell combinations.

        Returns:
            True if the combination was found and applied, False otherwise.
        """
        raise NotImplementedError("This method should be implemented by subclasses.")


class SpellCombinations(EventListener):
    """Manager for spell combinations that listens to spell events.

    This class manages a collection of SpellCombination instances and automatically
    checks them whenever a spell is added to the Aura.
    """

    def __init__(self):
        """Initialize a new SpellCombinations manager with an empty combination list."""
        self._combinations: list[SpellCombination] = []

    def on_spell_event(self, aura: "Aura", event: AuraEvent) -> None:
        """Check for combinations when spells are added.

        Args:
            aura: The Aura instance where the event occurred.
            event: The event that was triggered.
        """
        if isinstance(event, AddSpellEvent):
            for combo in self._combinations:
                combo.check(aura)

    def add(self, combination: SpellCombination) -> None:
        """Add a spell combination to the manager.

        Args:
            combination: The SpellCombination instance to register.
        """
        self._combinations.append(combination)

    def remove(self, combination: SpellCombination) -> None:
        """Remove a spell combination from the manager.

        Args:
            combination: The SpellCombination instance to unregister.
        """
        if combination in self._combinations:
            self._combinations.remove(combination)

    def __len__(self) -> int:
        """Return the number of registered spell combinations.

        Returns:
            The count of spell combinations currently registered.
        """
        return len(self._combinations)

    def __iter__(self):
        """Return an iterator over the registered spell combinations.

        Returns:
            An iterator over the list of spell combinations.
        """
        return iter(self._combinations)

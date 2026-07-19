try:
    from collections.abc import Callable, Iterator
except ImportError:
    pass


class Duration:
    """Tracks elapsed time against a fixed length, reporting when it expires."""

    def __init__(self, length: float) -> None:
        self._length: float = length
        self._elapsed: float = 0.0

    def update(self, elapsed_time: float) -> bool:
        """Adds ``elapsed_time`` and returns whether the duration has expired."""
        self._elapsed += elapsed_time

        return self.is_expired

    def reset(self) -> None:
        """Resets the elapsed time to zero."""
        self._elapsed = 0.0

    @property
    def length(self) -> float:
        """The total length of the duration."""
        return self._length

    @length.setter
    def length(self, value: float) -> None:
        self._length = value

    @property
    def elapsed(self) -> float:
        """The time elapsed since the start of the duration."""
        return self._elapsed

    @property
    def remaining(self) -> float:
        """The time until the duration expires, never negative."""
        return max(0.0, self._length - self._elapsed)

    @property
    def is_expired(self) -> bool:
        """Whether the elapsed time has reached the length."""
        return self._elapsed >= self._length


class ValueModifier:
    """Applies a temporary multiplier to a value, expiring after a duration."""

    def __init__(self, multiplier: float, duration: float) -> None:
        self._multiplier = multiplier
        self._duration = Duration(duration)

    def update(self, elapsed_time: float) -> bool:
        """Advances the modifier and returns whether it has expired."""
        return self._duration.update(elapsed_time)

    @property
    def multiplier(self) -> float:
        return self._multiplier

    @multiplier.setter
    def multiplier(self, value: float) -> None:
        self._multiplier = value

    @property
    def duration(self) -> Duration:
        return self._duration


class ValueModifiers:
    """Manages a collection of ``ValueModifier`` objects, notifying an optional
    callback whenever the collection changes."""

    def __init__(self, modifiers_changed: Callable | None = None) -> None:
        self._modifiers: list[ValueModifier] = []
        self._modifiers_changed = modifiers_changed

    def _notify_modifiers_changed(self) -> None:
        if self._modifiers_changed:
            self._modifiers_changed()

    def add(self, modifier: ValueModifier) -> bool:
        """Adds ``modifier`` if not already present, returning whether it was added."""
        if modifier not in self._modifiers:
            self._modifiers.append(modifier)
            self._notify_modifiers_changed()
            return True

        return False

    def remove(self, modifier: ValueModifier) -> None:
        """Removes ``modifier`` if present."""
        if modifier in self._modifiers:
            self._modifiers.remove(modifier)
            self._notify_modifiers_changed()

    def update(self, elapsed_time: float) -> None:
        """Advances all modifiers, dropping any that have expired."""
        modifiers_to_remove = []
        for modifier in self._modifiers:
            if modifier.update(elapsed_time):
                modifiers_to_remove.append(modifier)

        for modifier in modifiers_to_remove:
            self._modifiers.remove(modifier)

        if len(modifiers_to_remove) > 0:
            self._notify_modifiers_changed()

    def modify(self, base_value: float) -> float:
        """Returns ``base_value`` with every active modifier's multiplier applied."""
        modified_value = base_value
        for modifier in self._modifiers:
            modified_value *= modifier.multiplier

        return modified_value

    def __len__(self) -> int:
        return len(self._modifiers)

    def __iter__(self) -> Iterator[ValueModifier]:
        return iter(self._modifiers)


class ValueWithModifiers:
    """A value that can be modified by a set of multipliers."""

    def __init__(self, base_value: float = 0.0, value_changed: Callable | None = None) -> None:
        self._base: float = base_value
        self._value: float = base_value
        self._value_changed = value_changed
        self._modifiers: ValueModifiers = ValueModifiers(self._update_value)

    def _update_value(self) -> None:
        """Recomputes the modified value, then fires the change callback if set."""
        self._value = self._modifiers.modify(self._base)
        if self._value_changed:
            self._value_changed()

    def update(self, elapsed_time: float) -> None:
        """Advances the modifiers, expiring any that have elapsed."""
        self._modifiers.update(elapsed_time)

    @property
    def base(self) -> float:
        return self._base

    @base.setter
    def base(self, value: float) -> None:
        self._base = value
        self._update_value()

    @property
    def modifiers(self) -> ValueModifiers:
        return self._modifiers

    @property
    def value(self) -> float:
        """The base value with all active modifiers applied."""
        return self._value


class MinMaxValue:
    """A value clamped between a minimum and a dynamic maximum."""

    def __init__(self, value: float, min: float, max: float) -> None:
        self._value = value
        self._min = min
        self._max = ValueWithModifiers(base_value=max, value_changed=self._clamp_value)

    def _clamp_value(self) -> None:
        """Clamps the current value between min and max."""
        self._value = max(self.min, min(self._value, self.max.value))

    def update(self, elapsed_time: float) -> None:
        """Advances the maximum's modifiers, which may lower the clamp ceiling."""
        self._max.update(elapsed_time)

    @property
    def value(self) -> float:
        """The current value, always within ``[min, max]``."""
        return self._value

    @value.setter
    def value(self, value: float) -> None:
        self._value = value
        self._clamp_value()

    @property
    def min(self) -> float:
        return self._min

    @min.setter
    def min(self, value: float) -> None:
        self._min = value
        self._clamp_value()

    @property
    def max(self) -> ValueWithModifiers:
        """The dynamic maximum, including active modifiers."""
        return self._max


class Counter:
    """A counter for tracking attributes like spell hits."""

    def __init__(self, max: int) -> None:
        self._max: int = max
        self._count: int = 0

    def increment(self) -> bool:
        """Increments the count by one, returning whether the maximum was reached."""
        self._count = min(self._count + 1, self._max)

        return self._count >= self._max

    def reset(self) -> None:
        """Resets the count to zero."""
        self._count = 0

    @property
    def count(self) -> int:
        return self._count

    @property
    def max(self) -> int:
        return self._max

    @property
    def is_max(self) -> bool:
        """Whether the count has reached the maximum."""
        return self._count >= self._max

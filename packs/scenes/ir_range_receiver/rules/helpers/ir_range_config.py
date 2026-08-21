"""``IrRangeConfig`` -- immutable scene configuration for ir_range_receiver.

Holds the three tunables seeded via ``initial_data`` (all ``ir_range_*`` seed
keys): the rolling-window length and silence timeout the
``ReceptionQualityMeter`` uses, and the green threshold that decides how
strict "Perfect" reception must be. ``IrRangeConfig.__init__`` takes
already-resolved values so it is unit-testable directly with no ``GameState``
involved; ``from_state`` is the factory that reads the flat seeded keys and
applies defaults.

``ir_range_config`` is a :class:`engine.state.StateSlot` callable accessor: it
lazily builds the config from ``state`` on first use and caches it under a
single ``GameState`` key, mirroring the ``rlgl_config``/``tag_config``
precedent.
"""

from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass

from engine.state import GameState, StateSlot

_CONFIG_KEY: Final = "ir_range_config"


class IrRangeConfig:
    """Immutable tunable configuration for the ir_range_receiver scene.

    All values are already-resolved (no ``GameState`` knowledge), so this can
    be constructed directly in tests. Use :meth:`from_state` to build one
    from a seeded ``GameState``.
    """

    __slots__ = ("green_threshold", "silence_timeout", "window_seconds")

    def __init__(
        self, window_seconds: float, silence_timeout: float, green_threshold: float
    ) -> None:
        self.window_seconds = window_seconds
        self.silence_timeout = silence_timeout
        self.green_threshold = green_threshold

    @classmethod
    def from_state(cls, state: GameState) -> IrRangeConfig:
        """Build a config from the flat seeded ``ir_range_*`` keys, applying defaults."""
        return cls(
            window_seconds=state.get("ir_range_window_seconds", 1.0),
            silence_timeout=state.get("ir_range_silence_timeout", 0.5),
            green_threshold=state.get("ir_range_green_threshold", 1.0),
        )


ir_range_config: StateSlot = StateSlot(_CONFIG_KEY, IrRangeConfig.from_state, IrRangeConfig)

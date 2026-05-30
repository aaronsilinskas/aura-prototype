from __future__ import annotations

__all__ = [
    "EffectControls",
    "EffectReceipt",
    "GameState",
    "NetworkControls",
    "SceneControls",
    "Scope",
    "ScopeValue",
]

try:
    from typing import Final
except ImportError:
    pass  # Not available on CircuitPython

try:
    from typing import TypeVar

    T = TypeVar("T")
except ImportError:
    pass  # Not available on CircuitPython

from engine.events import Event


class ScopeValue:
    """A routing token that identifies one or more outputs.

    Routing model:
      - ``keys`` is the flat tuple of routing strings ``EffectManager`` iterates
        to dispatch to outputs.  Leaf scopes have one key; composite scopes
        expand to the union of their members' keys.
      - ``members`` holds the constituent ``ScopeValue`` instances.  For leaf
        scopes ``members == [self]``.
    Construction:
      - Use the constants on ``Scope`` rather than constructing directly.
    """

    __slots__ = ("_value", "keys", "members")

    def __init__(self, value: str, members: list[ScopeValue] | None = None) -> None:
        self._value: str = value
        if members is None:
            self.members: list[ScopeValue] = [self]
            self.keys: tuple[str, ...] = (value,)
        else:
            self.members = members
            self.keys = tuple(k for m in self.members for k in m.keys)

    def __repr__(self) -> str:
        return self._value


class Scope:
    """Namespace of ``ScopeValue`` constants for routing effects to outputs.

    Usage:
      - ``PERSONAL`` — local player's device only.
      - ``DIRECTIONAL`` — the direction indicator the player is pointing.
      - ``Global.*`` — shared outputs targeting all players.
      - ``ALL`` — every output; use when the scope should be universal
        (e.g. clearing all active effects).
    """

    class Global:
        """Shared outputs that target all players.

        Use ``MAIN``, ``BUFF``, or ``DEBUFF`` to target a specific zone.
        Use ``ALL`` to address every global zone without differentiation.
        """

        MAIN: Final = ScopeValue("global.main")  # primary effect area (e.g. active spell)
        BUFF: Final = ScopeValue("global.buff")  # positive status effects
        DEBUFF: Final = ScopeValue("global.debuff")  # negative status effects
        ALL: Final = ScopeValue(
            "global.all", [MAIN, BUFF, DEBUFF]
        )  # entire global area, no differentiation

    PERSONAL: Final = ScopeValue("personal")  # only the local player's device
    DIRECTIONAL: Final = ScopeValue("directional")  # the direction the player is pointing
    ALL: Final = ScopeValue(
        "all", [PERSONAL, DIRECTIONAL, Global.ALL]
    )  # every scope, including all global zones


class SceneControls:
    """Abstract interface for scene transitions called from within game rules.

    All methods raise ``NotImplementedError`` by default.  ``SceneManager``
    injects itself as the live implementation; standalone callers (e.g. rule
    unit tests) pass the base ``SceneControls()`` instance, which raises on
    any call.

    Transitions are deferred to end-of-tick — the transition is applied after
    ``engine.update(state)`` returns, not immediately inside the rule.
    """

    __slots__ = ()

    def load(self, name: str) -> None:
        """Replace the entire scene stack with the named scene."""
        raise NotImplementedError

    def overlay(self, name: str) -> None:
        """Push the named scene on top, suspending the current scene."""
        raise NotImplementedError

    def pop(self) -> None:
        """Unload the top scene and restore the scene below it."""
        raise NotImplementedError


class NetworkControls:
    """Abstract interface for network transmit operations called from within game rules.

    All methods raise ``NotImplementedError`` by default.  ``HardwareNetworkControls``
    in ``engine/network.py`` provides the live hardware-backed implementation.

    Transmits are always broadcast — no recipient parameter; player identity is
    encoded in the payload if needed.
    """

    __slots__ = ()

    def send_ir(self, data: bytes) -> None:
        """Transmit an IR packet."""
        raise NotImplementedError

    def send_radio(self, data: bytes) -> None:
        """Transmit a radio packet."""
        raise NotImplementedError


class EffectReceipt:
    """Opaque handle returned when an effect is started.

    Uniquely identifies a single running effect instance. Call ``stop()`` to
    request that the effect be stopped on the next tick.
    """

    __slots__ = ("id", "_stopped")

    def __init__(self, effect_id: int) -> None:
        self.id: int = effect_id
        self._stopped: bool = False

    def stop(self) -> None:
        """Request that this effect be stopped on the next tick (idempotent)."""
        self._stopped = True

    def is_stopped(self) -> bool:
        """Return ``True`` if ``stop()`` has been called on this receipt."""
        return self._stopped

    def __repr__(self) -> str:
        return f"EffectReceipt(id={self.id})"


class EffectControls:
    """Read-only effect-control interface exposed to game rules via GameState.

    Provides effect start/stop operations only. The update() tick is
    intentionally excluded so rules cannot advance the effect loop.
    """

    def set_effect(
        self, scope: ScopeValue, name: str, level: int, options: dict[str, object]
    ) -> EffectReceipt:
        """Stop any effect(s) currently running in scope, then start name."""
        raise NotImplementedError

    def add_effect(
        self, scope: ScopeValue, name: str, level: int, options: dict[str, object]
    ) -> EffectReceipt:
        """Start name in scope without stopping existing effects."""
        raise NotImplementedError

    def stop_effect(self, scope: ScopeValue) -> None:
        """Stop all effects whose keys overlap scope."""
        raise NotImplementedError


class GameState:
    """Portable game context passed to every rule handler on every tick.

    Create via ``GameEngine.create_state()`` for production use, or directly
    for rule unit tests.  Data stored via ``state.set()`` survives across
    ticks when the same ``GameState`` instance is passed to each
    ``engine.update(state)`` call.

    Provides access to time information, the effect controls interface for
    starting and stopping effects, and ``queue_event`` so rules can enqueue
    events without holding a ``GameEngine`` reference.

    Time values are read-only; use ``state.elapsed`` and ``state.total`` to
    read per-tick and cumulative time.
    """

    __slots__ = (
        "_data",
        "_elapsed",
        "_queue",
        "_total",
        "effect_controls",
        "network_controls",
        "scene_controls",
    )

    def __init__(
        self,
        effect_controls: EffectControls,
        scene_controls: SceneControls,
        network_controls: NetworkControls | None = None,
        data: dict[str, object] | None = None,
    ) -> None:
        self.effect_controls = effect_controls
        self.scene_controls = scene_controls
        self.network_controls = (
            network_controls if network_controls is not None else NetworkControls()
        )
        self._queue: list[Event] = []
        self._data: dict[str, object] = data if data is not None else {}
        self._elapsed: float = 0.0
        self._total: float = 0.0

    @property
    def elapsed(self) -> float:
        """Seconds elapsed during the most recent tick."""
        return self._elapsed

    @property
    def total(self) -> float:
        """Cumulative seconds elapsed since the engine started."""
        return self._total

    def get(self, key: str, default: T) -> T:
        """Return the stored value for *key*, or *default* if absent."""
        if key in self._data:
            return self._data[key]  # type: ignore[return-value]
        return default

    def set(self, key: str, value: object) -> None:
        """Store *value* under *key*."""
        self._data[key] = value

    def pop(self, key: str, type_: type[T]) -> T:
        """Remove and return the value at *key*, validating its type first.

        Raises:
            KeyError: if *key* is absent.
            ValueError: if the stored value is not an instance of *type_*;
                the key is **not** removed in this case.
        """
        if key not in self._data:
            raise KeyError(key)
        value = self._data[key]
        if not isinstance(value, type_):
            raise ValueError("Key '" + key + "' value is not an instance of " + type_.__name__)
        del self._data[key]
        return value  # type: ignore[return-value]

    def delete(self, key: str) -> None:
        """Remove *key* from state; no-op if absent."""
        self._data.pop(key, None)

    def has(self, key: str) -> bool:
        """Return ``True`` if *key* is present in state."""
        return key in self._data

    def __contains__(self, key: object) -> bool:
        """Support ``"key" in state`` membership tests."""
        return key in self._data

    def queue_event(self, event: Event) -> None:
        """Enqueue an event for processing on the current or next update."""
        self._queue.append(event)

    def clear_queue(self) -> None:
        """Discard all pending events without processing them."""
        self._queue = []

    def _update_time(self, elapsed: float, total: float) -> None:
        """Refresh time values from the engine's timer. Called only by GameEngine."""
        self._elapsed = elapsed
        self._total = total

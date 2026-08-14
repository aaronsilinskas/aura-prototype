from __future__ import annotations

__all__ = [
    "EffectAdmin",
    "EffectControls",
    "EffectReceipt",
    "GameState",
    "MergeStrategy",
    "NetworkControls",
    "SceneControls",
    "Scope",
    "ScopeValue",
    "StateSlot",
]

try:
    from collections.abc import Callable
    from typing import Final, TypeVar

    T = TypeVar("T")
except ImportError:
    pass  # Not available on CircuitPython

from effects.effect import PixelBuffer
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
      - ``AMBIENT`` — long-running background effects.
      - ``Global.*`` — shared outputs targeting all players.
      - ``NON_AMBIENT`` — every non-ambient scope (PERSONAL, DIRECTIONAL, Global.ALL).
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
    AMBIENT: Final = ScopeValue("ambient")  # long-running background effects
    NON_AMBIENT: Final = ScopeValue(
        "non_ambient", [PERSONAL, DIRECTIONAL, Global.ALL]
    )  # all non-ambient scopes
    ALL: Final = ScopeValue(
        "all", [PERSONAL, DIRECTIONAL, Global.ALL, AMBIENT]
    )  # every scope, including all global zones and ambient


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
    in ``hardware/shared/network_controls.py`` provides the live hardware-backed
    implementation.

    Transmits are always broadcast — no recipient parameter; player identity is
    encoded in the payload if needed.
    """

    __slots__ = ()

    def send_ir(self, data: bytes, emitter: str) -> None:
        """Broadcast an IR packet on the named emitter, fire-and-forget."""
        raise NotImplementedError

    def send_radio(self, data: bytes) -> None:
        """Transmit a radio packet."""
        raise NotImplementedError


class EffectReceipt:
    """Identity and lifecycle handle for a single running effect instance.

    Call ``stop()`` to request removal on the next tick; ``is_stopped()``
    reports whether that has happened.

    ``brightness`` and ``loudness`` are runtime intensity controls in
    ``[0.0, 1.0]`` (default ``1.0``) that rules set directly
    (``receipt.brightness = x``) to vary an effect's intensity without
    restarting it. Assigning a value outside that range raises
    ``ValueError``. The pixel merge layer (``engine.effects.merge``) reads
    ``brightness``; the voice pool (``hardware.shared.voice_pool``) reads
    ``loudness``.
    """

    __slots__ = ("_brightness", "_loudness", "_stopped", "id")

    def __init__(self, effect_id: int) -> None:
        self.id: int = effect_id
        self._stopped: bool = False
        self._brightness: float = 1.0
        self._loudness: float = 1.0

    @property
    def brightness(self) -> float:
        return self._brightness

    @brightness.setter
    def brightness(self, value: float) -> None:
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"brightness must be in [0.0, 1.0], got {value!r}")
        self._brightness = value

    @property
    def loudness(self) -> float:
        return self._loudness

    @loudness.setter
    def loudness(self, value: float) -> None:
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"loudness must be in [0.0, 1.0], got {value!r}")
        self._loudness = value

    def stop(self) -> None:
        """Request that this effect be stopped on the next tick (idempotent)."""
        self._stopped = True

    def is_stopped(self) -> bool:
        """Return ``True`` if ``stop()`` has been called on this receipt."""
        return self._stopped

    def __repr__(self) -> str:
        return f"EffectReceipt(id={self.id})"


class MergeStrategy:
    """Per-scope policy compositing a scope's layered effect buffers into one region buffer.

    This project's ``Protocol`` substitute: a plain base class whose methods
    only raise ``NotImplementedError``. Subclasses hold no per-instance state,
    so each ships as a module-level singleton (``SPLIT``, ``ADDITIVE`` in
    ``engine.effects.merge``). Lives here rather than in ``engine.effects.merge``
    because that module imports ``EffectReceipt`` from this one; defining the
    base class in ``engine.effects.merge`` would make ``EffectControls.set_merge_strategy``
    below need a circular import back into it.
    """

    def prepare_buffers(self, buffers: list[PixelBuffer]) -> None:
        """Resize *buffers* to this strategy's layout ahead of the next ``merge`` call."""
        raise NotImplementedError

    def merge(
        self, buffers: list[PixelBuffer], receipts: list[EffectReceipt | None]
    ) -> PixelBuffer:
        """Composite *buffers* (each scaled by its parallel receipt's brightness) into buffers[0].

        Returns ``buffers[0]``, resized to the full region capacity.
        """
        raise NotImplementedError


class EffectControls:
    """Rule-facing effect-control interface exposed to game rules via GameState.

    Provides effect start/stop and merge-strategy operations only. The update()
    tick is intentionally excluded so rules cannot advance the effect loop.
    Scene-transition operations (local effect registry swaps, merge-strategy
    snapshot/reset/apply) live on the separate ``EffectAdmin`` face, reached
    through ``SceneManager`` rather than through this interface.
    """

    def set_effect(self, scope: ScopeValue, name: str, options: dict[str, object]) -> EffectReceipt:
        """Stop any effect(s) currently running in scope, then start name."""
        raise NotImplementedError

    def add_effect(self, scope: ScopeValue, name: str, options: dict[str, object]) -> EffectReceipt:
        """Start name in scope without stopping existing effects."""
        raise NotImplementedError

    def stop_effect(self, scope: ScopeValue) -> None:
        """Stop all effects whose keys overlap scope."""
        raise NotImplementedError

    def set_merge_strategy(self, scope: ScopeValue, strategy: MergeStrategy) -> None:
        """Set the merge strategy for every scope key in scope.keys.

        Ticks after the next ``prepare_buffers`` call route through the new
        strategy. Defaults to ``SPLIT`` for every scope key; ``SceneManager``
        resets the choice on ``load`` and captures/applies it across
        ``overlay``/``pop`` through the separate ``EffectAdmin`` face.
        """
        raise NotImplementedError


class EffectAdmin:
    """Scene-transition-facing effect interface, reserved for ``SceneManager``.

    Carries the operations ``EffectControls`` deliberately sheds so rules never
    see them: swapping the active scene's local effect registry and
    snapshotting/resetting/applying the per-scope merge strategy map.
    ``SceneManager`` holds an injected ``EffectAdmin`` handle (wired to the same
    instance as ``state.effect_controls``, e.g. the single ``EffectManager``)
    and drives every transition call through it, never through
    ``state.effect_controls``. All four methods raise ``NotImplementedError``
    by default.
    """

    def reset_merge_strategies(self) -> None:
        """Reset every registered scope key's merge strategy to ``SPLIT``.

        Called by ``SceneManager._do_load`` so no strategy choice survives a
        ``load``.
        """
        raise NotImplementedError

    def capture_merge_strategies(self) -> dict[str, MergeStrategy]:
        """Return an independent snapshot of the current per-scope merge strategy map.

        The live map is left in place, so an overlay starts by inheriting the
        underlying scene's current choices while remaining free to change
        them. Called by ``SceneManager._do_overlay``; the returned snapshot
        rides in the scene stack entry the overlay pushes, to be applied back
        on the matching ``pop``.
        """
        raise NotImplementedError

    def apply_merge_strategies(self, snapshot: dict[str, MergeStrategy]) -> None:
        """Direct-install *snapshot* as the live per-scope merge strategy map.

        Called by ``SceneManager._do_pop`` with the popped scene stack entry's
        saved snapshot, discarding any ``set_merge_strategy`` calls made during
        the popped overlay.
        """
        raise NotImplementedError

    def set_local_effects(self, local_registry: object) -> None:
        """Push the active scene's local effect registry into the effect system.

        Called by ``SceneManager`` on every transition so that
        ``scene.<effect>`` names resolve against the top-of-stack scene's
        local effects. Pass ``None`` when the scene stack empties so that
        ``scene.`` lookups fail immediately rather than resolving against a
        stale registry.
        """
        raise NotImplementedError

    def set_allowed_packs(self, names: frozenset[str] | None) -> None:
        """Install the active scene's declared effect-pack names.

        Called by ``SceneManager`` on every transition, right beside
        ``set_local_effects``, so a ``pack.effect`` reference only resolves
        when *pack* is one of the top-of-stack scene's declared
        ``effect_packs``. Pass ``None`` when the scene stack empties so that
        ``pack.`` lookups fail closed ("no active scene") rather than
        resolving unrestricted. ``scene.``-prefixed names are unaffected.
        """
        raise NotImplementedError


class StateSlot:
    """Callable accessor that owns the get-or-create-and-revalidate pattern for a GameState key.

    Constructed once at module load; the single ``# type: ignore[return-value]`` cast lives
    here so call sites are cast-free.
    """

    __slots__ = ("_expected_class", "_factory", "key")

    def __init__(
        self,
        key: str,
        factory: Callable[[GameState], object],
        expected_class: type[T],
    ) -> None:
        self.key: str = key
        self._factory = factory
        self._expected_class = expected_class

    def __call__(self, state: GameState) -> T:
        """Return the value for *key*, creating and caching it on first use.

        Raises:
            ValueError: if the stored value is not an instance of *expected_class*.
        """
        if not state.has(self.key):
            state.set(self.key, self._factory(state))
        return state.get_or_none(self.key, self._expected_class)  # type: ignore[return-value]

    def is_in(self, state: GameState) -> bool:
        """Return True if this slot's key is present in *state*."""
        return state.has(self.key)


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
        "_len",
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
        queue_capacity: int = 8,
    ) -> None:
        self.effect_controls = effect_controls
        self.scene_controls = scene_controls
        self.network_controls = (
            network_controls if network_controls is not None else NetworkControls()
        )
        self._queue: list[Event | None] = [None] * queue_capacity
        self._len: int = 0
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

    def get_or_none(self, key: str, expected_class: type[T]) -> T | None:
        """Return the stored value for *key*, or ``None`` if absent.

        For optional/absent lookups, where ``get``'s required *default*
        is inconvenient. Mirrors ``SceneLocalRegistry.get``'s
        ``expected_class: type[T]`` type-hint convention: the
        ``isinstance`` check below lets the type checker narrow the
        return value to ``T | None`` without ``# type: ignore``.

        Raises:
            ValueError: if *key* is present but the stored value is not
                an instance of *expected_class*.
        """
        if key not in self._data:
            return None
        value = self._data[key]
        if not isinstance(value, expected_class):
            raise ValueError(f"Key '{key}' value is not an instance of {expected_class.__name__}")
        return value

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
            raise ValueError(f"Key '{key}' value is not an instance of {type_.__name__}")
        del self._data[key]
        return value  # type: ignore[return-value]

    def delete(self, key: str) -> None:
        """Remove *key* from state; no-op if absent."""
        self._data.pop(key, None)

    def has(self, key: str) -> bool:
        """Return ``True`` if *key* is present in state."""
        return key in self._data

    def __contains__(self, key: object) -> bool:
        return key in self._data

    @property
    def event_count(self) -> int:
        """Number of events currently queued (the queue's fill level)."""
        return self._len

    def event_at(self, index: int) -> Event:
        """Return the queued event at *index*.

        Valid for ``0 <= index < event_count``; the engine dispatches by
        iterating these indices rather than popping, so same-tick appended
        events are picked up by re-reading ``event_count``.
        """
        return self._queue[index]  # type: ignore[return-value]

    def queue_event(self, event: Event) -> None:
        """Enqueue an event for processing on the current or next update.

        Reuses a pre-allocated slot when one is free; only grows (and keeps the
        larger capacity) on overflow, so the steady state never allocates.
        """
        if self._len < len(self._queue):
            self._queue[self._len] = event
        else:
            self._queue.append(event)
        self._len += 1

    def reset_queue(self) -> None:
        """Drop all queued events, releasing their references, without allocating.

        Called by the engine after dispatching a tick's events.
        """
        self._reset_queue()

    def clear_queue(self) -> None:
        """Discard all pending events without processing them.

        Reserved for scene transitions (mirrors ``set_local_effects``); resets
        the queue in place without allocating.
        """
        self._reset_queue()

    def _reset_queue(self) -> None:
        """Empty the queue in place, keeping the backing list's capacity.

        Filled slots are nulled so the previous tick's event references are
        released promptly rather than pinned alive until a later slot reuse.
        """
        queue = self._queue
        i = 0
        n = self._len
        while i < n:
            queue[i] = None
            i += 1
        self._len = 0

    def _update_time(self, elapsed: float, total: float) -> None:
        """Refresh time values from the engine's timer. Called only by GameEngine."""
        self._elapsed = elapsed
        self._total = total

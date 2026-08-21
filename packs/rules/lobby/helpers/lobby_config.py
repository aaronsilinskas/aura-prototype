"""``LobbyConfig`` — resolved, validated configuration for ``LobbySelectRule``.

Holds the ordered display scopes and ordered selectable entries read from a
scene's ``initial_data`` (see ``LobbySelectRule`` for the raw config shape).
``LobbyConfig.__init__`` takes already-resolved values so it is unit-testable
directly with no ``GameState`` involved; ``from_state`` is the factory that
reads the raw dict seeded at a given state key and resolves each scope string
to its engine ``ScopeValue`` via ``scope_by_name``. Lobby config has no
sensible per-field defaults (a missing entry list can't default to "no
scenes"), so a missing or malformed ``scopes``/``entries`` list raises rather
than silently falling back to something that would show the wrong scenes.

``scope_by_name`` is a small, lobby-local resolver: there is no engine-wide
``Scope.by_name`` today, and only this one consumer needs config strings
(``"personal"``, ``"global.main"``, ...) mapped to ``ScopeValue`` instances.
The mapping is built from ``str()`` of each ``Scope`` constant rather than
duplicating the strings by hand, so a future rename of a scope's internal
string representation fails loudly here instead of silently drifting.
"""

from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass  # Not available on CircuitPython

from engine.state import GameState, Scope, ScopeValue

_SCOPE_BY_NAME: Final = {
    str(Scope.PERSONAL): Scope.PERSONAL,
    str(Scope.DIRECTIONAL): Scope.DIRECTIONAL,
    str(Scope.AMBIENT): Scope.AMBIENT,
    str(Scope.Global.MAIN): Scope.Global.MAIN,
    str(Scope.Global.BUFF): Scope.Global.BUFF,
    str(Scope.Global.DEBUFF): Scope.Global.DEBUFF,
    str(Scope.Global.ALL): Scope.Global.ALL,
    str(Scope.NON_AMBIENT): Scope.NON_AMBIENT,
    str(Scope.ALL): Scope.ALL,
}


def scope_by_name(name: str) -> ScopeValue:
    """Resolve a lobby config scope string to its engine ``ScopeValue``.

    Raises:
        ValueError: if *name* does not match any known ``ScopeValue``.
    """
    scope = _SCOPE_BY_NAME.get(name)
    if scope is None:
        raise ValueError(f"Unknown lobby scope name: {name!r}")
    return scope


class LobbyEntry:
    """One selectable lobby entry: the scene it launches plus its preview effect."""

    __slots__ = ("effect", "options", "scene")

    def __init__(self, scene: str, effect: str, options: dict[str, object]) -> None:
        self.scene = scene
        self.effect = effect
        self.options = options


def _parse_entry(entry: dict[str, object]) -> LobbyEntry:
    scene = entry.get("scene")
    effect = entry.get("effect")
    if not scene or not effect:
        raise ValueError(f"Lobby entry missing 'scene' or 'effect': {entry!r}")
    options = entry.get("options", {})
    return LobbyEntry(scene=scene, effect=effect, options=options)  # type: ignore[arg-type]


class LobbyConfig:
    """Resolved, validated lobby configuration: ordered display scopes plus ordered entries.

    All values are already-resolved (no ``GameState`` knowledge), so this can
    be constructed directly in tests. Use :meth:`from_state` to build one from
    a scene's seeded ``initial_data``.

    Raises:
        ValueError: if *scopes* or *entries* is empty.
    """

    __slots__ = ("entries", "scopes")

    def __init__(self, scopes: list[ScopeValue], entries: list[LobbyEntry]) -> None:
        if not scopes:
            raise ValueError("Lobby config 'scopes' must be non-empty")
        if not entries:
            raise ValueError("Lobby config 'entries' must be non-empty")
        self.scopes = scopes
        self.entries = entries

    @classmethod
    def from_state(cls, state: GameState, config_key: str) -> LobbyConfig:
        """Build from the raw dict seeded at *config_key* in *state*.

        Raises:
            ValueError: if *config_key* is absent or not a dict, if
                ``scopes``/``entries`` is missing or empty, if any scope name
                is unknown, or if an entry is missing ``scene``/``effect``.
        """
        raw = state.get_or_none(config_key, dict)
        if raw is None:
            raise ValueError(f"Lobby config key {config_key!r} is missing or not a dict")

        scopes = [scope_by_name(name) for name in raw.get("scopes", [])]
        entries = [_parse_entry(entry) for entry in raw.get("entries", [])]
        return cls(scopes, entries)

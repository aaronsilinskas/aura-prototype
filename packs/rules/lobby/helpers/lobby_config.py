"""``LobbyConfig`` — resolved, validated configuration for ``LobbySelectRule``.

Holds the ordered display scopes and ordered selectable entries the ``lobby``
pack declares as its ``scopes`` and ``entries`` Settings (see
``LobbySelectRule`` for their shape). The scan checks only that each is a
list; the deep checks live here. ``LobbyConfig``'s constructor reads the
Settings view and resolves each scope string to its engine ``ScopeValue`` via
``scope_by_name``. Both Settings are required, with
no default (a missing entry list can't default to "no scenes"), and an empty
or malformed one raises rather than showing the wrong scenes. So does an entry
list the device can run none of: a lobby with nothing to offer fails loudly
rather than sitting dark.

``scope_by_name`` is a small, lobby-local resolver: there is no engine-wide
``Scope.by_name`` today, and only this one consumer needs config strings
(``"personal"``, ``"global.main"``, ...) mapped to ``ScopeValue`` instances.
The mapping is built from ``str()`` of each ``Scope`` constant rather than
duplicating the strings by hand, so a future rename of a scope's internal
string representation fails loudly here instead of silently drifting.
"""

from __future__ import annotations

try:
    from collections.abc import Callable
    from typing import Final
except ImportError:
    pass  # Not available on CircuitPython

from engine.settings import Settings
from engine.state import Scope, ScopeValue

NAMESPACE: Final = "lobby"

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


def scope_by_name(name: object) -> ScopeValue:
    """Resolve a lobby config scope string to its engine ``ScopeValue``.

    Raises:
        ValueError: if *name* does not match any known ``ScopeValue``.
    """
    scope = _SCOPE_BY_NAME.get(name) if isinstance(name, str) else None
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


def _parse_entry(entry: object) -> LobbyEntry:
    if not isinstance(entry, dict):
        raise ValueError(f"Lobby entry is not an object: {entry!r}")
    scene = entry.get("scene")
    effect = entry.get("effect")
    if not scene or not effect:
        raise ValueError(f"Lobby entry missing 'scene' or 'effect': {entry!r}")
    options = entry.get("options", {})
    return LobbyEntry(scene=scene, effect=effect, options=options)


class LobbyConfig:
    """Resolved, validated lobby configuration: ordered display scopes plus ordered entries.

    Built from the ``lobby`` pack's ``scopes`` and ``entries`` Settings. Keeps,
    in order, only the entries whose scene *can_run* accepts
    (``SceneControls.can_run`` on a device), so the lobby offers only scenes
    this prop can play. Every entry is checked before any is left out.

    Raises:
        ValueError: if an entry is not an object or is missing
            ``scene``/``effect``, if any scope name is unknown, if ``scopes``
            is empty, or if no entry is left: none was declared, or the device
            can run none of them.
    """

    __slots__ = ("entries", "scopes")

    def __init__(self, settings: Settings, can_run: Callable[[str], bool]) -> None:
        scope_names = settings.get_list(NAMESPACE, "scopes")
        entries = [_parse_entry(entry) for entry in settings.get_list(NAMESPACE, "entries")]
        playable = [entry for entry in entries if can_run(entry.scene)]
        if entries and not playable:
            raise ValueError("Lobby config 'entries' has no scene this device can run")
        scopes = [scope_by_name(name) for name in scope_names]
        if not scopes:
            raise ValueError("Lobby config 'scopes' must be non-empty")
        if not playable:
            raise ValueError("Lobby config 'entries' must be non-empty")
        self.scopes: list[ScopeValue] = scopes
        self.entries: list[LobbyEntry] = playable

"""ActiveSceneNamespace — the names the active scene can reach, and how they resolve.

Owns the ``scene.``/``<pack>.`` routing, the declared-pack gate, the failure
when no scene is installed, and the wording of every name resolution error.
Hardware must not import this module (import-linter enforces it).
"""

from __future__ import annotations

__all__ = [
    "ActiveSceneNamespace",
    "MissingPrefixError",
    "NoActiveSceneError",
    "UndeclaredPackError",
]

try:
    from typing import TYPE_CHECKING
except ImportError:
    TYPE_CHECKING = False

from engine.effects.manager import EffectBuilder
from engine.packs import PackRegistry, RegistryError, UnknownItemError, UnknownPackError

if TYPE_CHECKING:
    from engine.scene import SceneLocalRegistry

_SCENE_PREFIX = "scene"


class NoActiveSceneError(RegistryError):
    """A name was looked up before any scene was installed."""

    def __init__(self, name: str, kind: str) -> None:
        self.name = name
        self.kind = kind
        super().__init__(f"Cannot resolve {kind} '{name}': no scene is active")


class MissingPrefixError(RegistryError):
    """The name has no ``scene.`` or ``<pack>.`` prefix."""

    def __init__(self, name: str, kind: str) -> None:
        self.name = name
        self.kind = kind
        super().__init__(f"{kind.capitalize()} name '{name}' has no 'scene.' or '<pack>.' prefix")


class UndeclaredPackError(RegistryError):
    """The pack is installed, but the active scene does not declare it."""

    def __init__(self, name: str, kind: str, pack_name: str) -> None:
        self.name = name
        self.kind = kind
        self.pack_name = pack_name
        super().__init__(
            f"{kind.capitalize()} '{name}' uses pack '{pack_name}', "
            + "which the active scene does not declare in effect_packs"
        )


class ActiveSceneNamespace:
    """Resolves names against the scene view ``SceneManager`` last installed.

    Built once at composition from the Pack catalog's effect registry and pack
    sounds, with no scene installed. ``SceneManager`` calls ``install`` once
    per activation (load, overlay, pop). Nothing is cached between lookups
    beyond what the registries cache themselves.
    """

    __slots__ = (
        "_declared_packs",
        "_effect_registry",
        "_known_packs",
        "_local_effects",
        "_local_sounds",
        "_pack_sounds",
    )

    def __init__(self, effect_registry: PackRegistry, pack_sounds: dict[str, str]) -> None:
        self._effect_registry: PackRegistry = effect_registry
        self._known_packs: frozenset[str] = frozenset(effect_registry.names())
        self._pack_sounds: dict[str, str] = pack_sounds
        self._local_effects: SceneLocalRegistry | None = None
        self._local_sounds: dict[str, str] = {}
        self._declared_packs: frozenset[str] | None = None

    def install(
        self,
        local_effects: SceneLocalRegistry | None,
        local_sounds: dict[str, str],
        declared_packs: frozenset[str],
    ) -> None:
        """Replace the scene view: its local effects and sounds, and its declared effect packs.

        *local_sounds* is a bare ``{stem: path}`` map; *declared_packs* holds the
        scene's ``effect_packs`` names. Once installed, lookups no longer fail
        with ``NoActiveSceneError``.
        """
        self._local_effects = local_effects
        self._local_sounds = local_sounds
        self._declared_packs = declared_packs

    def resolve_effect(self, name: str) -> tuple[EffectBuilder, str, str]:
        """Return ``(builder, pack_name, effect_name)`` for the qualified effect *name*.

        ``scene.<effect>`` resolves against the installed local effects (and
        ``pack_name`` is ``"scene"``); ``<pack>.<effect>`` against a shared
        pack the installed scene declared.

        Raises, in check order:
            MissingPrefixError: *name* has no prefix (even before any install).
            NoActiveSceneError: no scene has been installed.
            UnknownPackError: the pack is not an installed effect pack.
            UndeclaredPackError: the pack is installed but not declared.
            UnknownItemError: the scene's locals or the pack have no such effect.
            ItemTypeError, MissingItemAttributeError: the item's ``BUILD`` is
                bad or missing; propagated unchanged from the registry.
        """
        pack_name, item_name = self._split(name, "effect")
        if pack_name == _SCENE_PREFIX:
            local_effects = self._local_effects
            if local_effects is None:
                raise UnknownItemError(item_name, [], name=name, kind="effect")
            try:
                builder = local_effects.get(item_name, EffectBuilder)
            except UnknownItemError as exc:
                raise UnknownItemError(item_name, exc.available, name=name, kind="effect") from exc
        else:
            self._check_pack(name, "effect", pack_name)
            try:
                builder = self._effect_registry.get(pack_name, item_name, EffectBuilder)
            except UnknownItemError as exc:
                raise UnknownItemError(
                    item_name, exc.available, pack_name=pack_name, name=name, kind="effect"
                ) from exc
        return builder, pack_name, item_name

    def resolve_clip(self, name: str) -> str:
        """Return the WAV path for the qualified clip *name*.

        Routes like ``resolve_effect``: ``scene.<clip>`` against the installed
        local sounds, ``<pack>.<clip>`` against a declared effect pack's
        sounds. A clip inside a pack effect gets no allowance for that
        effect's own pack; every clip resolves against the active scene.

        Raises, in check order:
            MissingPrefixError: *name* has no prefix (even before any install).
            NoActiveSceneError: no scene has been installed.
            UnknownPackError: the pack is not an installed effect pack.
            UndeclaredPackError: the pack is installed but not declared.
            UnknownItemError: the scene or the pack has no such clip. A pack
                with no sounds is still known, so it lands here too.
        """
        pack_name, item_name = self._split(name, "clip")
        if pack_name == _SCENE_PREFIX:
            path = self._local_sounds.get(item_name)
            if path is None:
                raise UnknownItemError(
                    item_name, sorted(self._local_sounds), name=name, kind="clip"
                )
            return path
        self._check_pack(name, "clip", pack_name)
        path = self._pack_sounds.get(name)
        if path is None:
            prefix = pack_name + "."
            available = sorted(k[len(prefix) :] for k in self._pack_sounds if k.startswith(prefix))
            raise UnknownItemError(
                item_name, available, pack_name=pack_name, name=name, kind="clip"
            )
        return path

    def _split(self, name: str, kind: str) -> tuple[str, str]:
        """Split *name* into ``(prefix, item)``, failing before any scene check."""
        if "." not in name:
            raise MissingPrefixError(name, kind)
        if self._declared_packs is None:
            raise NoActiveSceneError(name, kind)
        pack_name, item_name = name.split(".", 1)
        return pack_name, item_name

    def _check_pack(self, name: str, kind: str, pack_name: str) -> None:
        if pack_name not in self._known_packs:
            raise UnknownPackError(pack_name, name=name, kind=kind)
        if pack_name not in self._declared_packs:
            raise UndeclaredPackError(name, kind, pack_name)

import os

import engine._path as _path


def scan_sound_dir(path: str) -> dict[str, str]:
    """Return a stem → WAV path map for every ``*.wav`` file directly in *path*.

    Mirrors ``scan_item_names``'s (``engine.packs``) stem-is-the-name rule, but for
    audio clips instead of pack items.  A missing or non-directory *path* yields an
    empty map rather than raising — callers with no wrapping ``scan_dir`` to guard
    the check (unlike ``scan_item_names``, whose callers check first) can call this
    directly.
    """
    sounds: dict[str, str] = {}
    if not _path.isdir(path):
        return sounds
    for fname in os.listdir(path):
        if not fname.endswith(".wav"):
            continue
        full_path = _path.join(path, fname)
        if _path.isdir(full_path):
            continue
        stem = fname[:-4]
        sounds[stem] = full_path
    return sounds


class AudioOverlayAdmin:
    """Scene-transition-facing seam for swapping the active scene's sound overlay.

    Carries the one operation a scene transition needs on ``AudioRegistry`` — mirrors
    ``EffectAdmin.set_local_effects``, keeping ``SceneManager``'s two admin seams
    (effects, audio) shaped the same way. Reserved for ``SceneManager``: game rules
    never call it. Raises ``NotImplementedError`` by default.
    """

    def set_scene_sounds(self, sounds: dict[str, str] | None) -> None:
        """Install *sounds* (bare ``{stem: path}``) as the active scene overlay.

        Called by ``SceneManager`` on every transition so ``scene.<clip>`` names
        resolve against the top-of-stack scene's sounds. Pass ``None`` when the
        active scene has no sounds (or the scene stack empties) so ``scene.``
        lookups fail immediately rather than resolving against a stale overlay.
        """
        raise NotImplementedError

    def set_allowed_packs(self, names: frozenset[str] | None) -> None:
        """Install *names* as the active scene's declared effect-pack names.

        Called by ``SceneManager`` at every transition, right beside
        ``set_scene_sounds``, with the same ``frozenset`` it derives for
        ``EffectAdmin.set_allowed_packs`` — reused, not re-derived — so that
        ``pack.<clip>`` resolution is bounded by declaration the same way
        ``pack.<effect>`` resolution is. Pass ``None`` to fail closed — no
        ``pack.<clip>`` name resolves until a scene installs its declared set.
        """
        raise NotImplementedError


class AudioRegistry(AudioOverlayAdmin):
    """Resolves a qualified clip name to a WAV path by prefix routing.

    Holds two maps: a **base** (``<pack>.<stem>`` → path), populated by scanning
    an effect pack's ``sounds/`` folder via ``scan_pack_sounds`` — shared and
    cross-scene, mirroring how effect packs are shared; and a swappable **scene
    overlay** (bare ``stem`` → path), installed via ``set_scene_sounds`` (the
    ``AudioOverlayAdmin`` face) — private to whichever scene is active.

    ``path`` routes exactly like ``EffectResolver``: the ``scene`` prefix reaches
    the overlay, any other prefix reaches the base, keyed by the full
    ``<pack>.<stem>`` name. An unprefixed name, or a name absent from its routed
    map, raises rather than returning ``None`` — a bad clip reference (typo or a
    missing/misnamed file) surfaces the same way a bad effect name does.

    The base branch is further gated by the ``pack.`` membership rule: a
    ``<pack>.<stem>`` name only resolves when *pack* is in the allowed set
    installed via ``set_allowed_packs`` (the ``AudioOverlayAdmin`` face),
    mirroring ``EffectResolver._resolve_pack``. ``None`` installed (the
    default) means no active scene and fails closed.
    """

    __slots__ = ("_allowed_packs", "_base", "_overlay")

    def __init__(self) -> None:
        self._base: dict[str, str] = {}
        self._overlay: dict[str, str] | None = None
        self._allowed_packs: frozenset[str] | None = None

    def scan_pack_sounds(self, pack_name: str, path: str) -> None:
        """Scan *path* and merge its clips into the base as ``<pack_name>.<stem>``.

        Qualifying every stem with *pack_name* is what lets two packs each ship a
        same-named clip (e.g. both a ``win.wav``) without colliding in the base.
        """
        for stem, clip_path in scan_sound_dir(path).items():
            self._base[f"{pack_name}.{stem}"] = clip_path

    def set_scene_sounds(self, sounds: dict[str, str] | None) -> None:
        self._overlay = sounds

    def set_allowed_packs(self, names: frozenset[str] | None) -> None:
        self._allowed_packs = names

    def path(self, name: str) -> str:
        """Return the WAV path *name* resolves to.

        *name* must be ``"scene.<stem>"`` (routes to the active scene overlay) or
        ``"<pack>.<stem>"`` (routes to the shared base, gated by the ``pack.``
        membership rule — see ``set_allowed_packs``).

        Raises:
            ValueError: *name* carries no ``.`` prefix, or resolves in neither
                the routed overlay nor the routed base; or, for a ``<pack>.``
                name, no active scene is installed or *pack* is not declared
                in the active scene's ``effect_packs``.
        """
        if "." not in name:
            raise ValueError(
                f"Clip name '{name}' missing prefix (expected 'scene.clip' or 'pack.clip')"
            )
        prefix, stem = name.split(".", 1)

        if prefix == "scene":
            if self._overlay is None or stem not in self._overlay:
                raise ValueError(f"Unknown scene sound '{name}'")
            return self._overlay[stem]

        if self._allowed_packs is None:
            raise ValueError(
                f"Clip name '{name}' references pack '{prefix}' but no scene is active"
            )
        if prefix not in self._allowed_packs:
            raise ValueError(
                f"Sound pack '{prefix}' is not declared in the active scene's effect_packs"
            )

        if name not in self._base:
            raise ValueError(f"Unknown sound '{name}'")
        return self._base[name]

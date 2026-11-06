"""Pack catalog — one scan of every pack root into the registries callers use."""

from __future__ import annotations

__all__ = [
    "DuplicateNameError",
    "IncompatiblePackError",
    "MalformedManifestError",
    "MalformedSceneError",
    "MalformedVersionError",
    "MissingRootError",
    "PackCatalog",
    "PackScanError",
    "ReservedNameError",
    "SceneDeclarationError",
    "SettingOverrideError",
    "UnknownDeclaredPackError",
    "read_manifest_declarations",
    "scan_pack_roots",
]

import json
import os
import sys

import engine._path as _path
from engine.packs import PackRegistry, _PackEntry, scan_item_names
from engine.scene import PackReference, SceneLocalRegistry, SceneRegistry, _SceneEntry
from engine.settings import (
    SettingDeclaration,
    Settings,
    SettingValueError,
    parse_declarations,
    resolve_settings,
)
from engine.version import Version

_REQUIRED_SCENE_KEYS = ("version", "effect_packs", "rule_packs")

_SCENE_KEYS = (*_REQUIRED_SCENE_KEYS, "settings", "ir_codec")

_PACK_REFERENCE_KEYS = ("name", "version", "settings")

# The attribute each kind's items export, in packs and scenes alike.
_EXPORT_ATTR = {"effects": "BUILD", "rules": "RULE"}

# The Pack manifest each kind's packs carry; a folder without one is not a pack.
_MANIFEST_NAME = {"effects": "effects.json", "rules": "rules.json"}

_SOUND_EXTENSIONS = (".wav",)

# The namespace of a scene's own Settings; no pack may take the name.
_SCENE_NAMESPACE = "scene"

# What one scene's ``setting_overrides`` may hold, mirroring ``scene.json``.
_OVERRIDE_KEYS = ("settings", "effect_packs", "rule_packs")


class PackScanError(ValueError):
    """Base class for every failure raised while scanning pack roots.

    The files on disk are wrong; unrelated to the lookup-time ``RegistryError``
    family, raised after a good scan.
    """


class MissingRootError(PackScanError):
    """A pack root passed to ``scan_pack_roots`` does not exist."""

    def __init__(self, root: str) -> None:
        self.root = root
        super().__init__(f"Pack root '{root}' does not exist")


class DuplicateNameError(PackScanError):
    """A pack, scene or root folder name was found at two paths.

    Two roots with one folder name would share an import prefix; a pack or
    scene under two roots would let one silently override the other.
    """

    def __init__(self, name: str, first_path: str, second_path: str) -> None:
        self.name = name
        self.first_path = first_path
        self.second_path = second_path
        super().__init__(f"Name '{name}' found at both '{first_path}' and '{second_path}'")


class ReservedNameError(PackScanError):
    """A pack is named ``scene``, the prefix reserved for scene-local names."""

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(
            f"'scene' is a reserved name and cannot be used as a pack name (found at '{path}')"
        )


class MalformedVersionError(PackScanError):
    """A version in *path* (a Pack manifest or ``scene.json``) is not ``'MAJOR.MINOR'``."""

    def __init__(self, path: str, value: object) -> None:
        self.path = path
        self.value = value
        super().__init__(f"Malformed version {value!r} in '{path}'; expected 'MAJOR.MINOR'")


class MalformedManifestError(PackScanError):
    """The Pack manifest at *path* cannot be used, for *reason*."""

    def __init__(self, path: str, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"Malformed pack manifest '{path}': {reason}")


class MalformedSceneError(PackScanError):
    """Scene *scene*'s ``scene.json`` at *path* cannot be used, for *reason*."""

    def __init__(self, scene: str, path: str, reason: str) -> None:
        self.scene = scene
        self.path = path
        self.reason = reason
        super().__init__(f"Scene '{scene}' has a malformed '{path}': {reason}")


class SceneDeclarationError(PackScanError):
    """Scene *scene* declares *pack* in ``effect_packs`` or ``rule_packs`` and cannot have it."""

    def __init__(self, scene: str, pack: str, message: str) -> None:
        self.scene = scene
        self.pack = pack
        super().__init__(message)


class UnknownDeclaredPackError(SceneDeclarationError):
    """A scene declares a pack that is not installed as that kind (effect or rule)."""

    def __init__(self, scene: str, pack: str, kind: str) -> None:
        self.kind = kind
        super().__init__(
            scene, pack, f"Scene '{scene}' declares {kind} pack '{pack}', which is not installed"
        )


class IncompatiblePackError(SceneDeclarationError):
    """A scene requires a pack version the installed one does not satisfy.

    Compatible means an equal major and an installed minor at least the required one.
    """

    def __init__(self, scene: str, pack: str, installed: Version, required: Version) -> None:
        self.installed = installed
        self.required = required
        super().__init__(
            scene,
            pack,
            f"Scene '{scene}' requires pack '{pack}' {required}, but {installed} is installed",
        )


class SettingOverrideError(SceneDeclarationError):
    """Scene *scene* cannot set Setting *setting* of *pack* (or ``"scene"``), for *reason*.

    The override names an undeclared Setting or gives a value of the wrong
    type, or the Setting is required and nothing set it.
    """

    def __init__(self, scene: str, pack: str, setting: str, reason: str) -> None:
        self.setting = setting
        self.reason = reason
        super().__init__(
            scene, pack, f"Scene '{scene}' cannot resolve {pack} Setting '{setting}': {reason}"
        )


class PackCatalog:
    """Everything installed under a device's pack roots, as found by ``scan_pack_roots``."""

    __slots__ = ("_effect_registry", "_pack_sounds", "_rule_registry", "_scene_registry")

    def __init__(
        self,
        effect_registry: PackRegistry,
        rule_registry: PackRegistry,
        scene_registry: SceneRegistry,
        pack_sounds: dict[str, str],
    ) -> None:
        self._effect_registry = effect_registry
        self._rule_registry = rule_registry
        self._scene_registry = scene_registry
        self._pack_sounds = pack_sounds

    @property
    def effect_registry(self) -> PackRegistry:
        """Effect packs; items export ``BUILD``."""
        return self._effect_registry

    @property
    def rule_registry(self) -> PackRegistry:
        """Rule packs; items export ``RULE``."""
        return self._rule_registry

    @property
    def scene_registry(self) -> SceneRegistry:
        """Scenes, each with its local effects, local rules and local sound map."""
        return self._scene_registry

    @property
    def pack_sounds(self) -> dict[str, str]:
        """A copy of the effect packs' sounds: ``<pack>.<stem>`` → WAV path."""
        return dict(self._pack_sounds)


def scan_pack_roots(
    roots: list[str],
    setting_overrides: dict[str, dict[str, dict]] | None = None,
) -> PackCatalog:
    """Scan the pack *roots*, in order, into one ``PackCatalog``.

    Every scene's ``effect_packs`` and ``rule_packs`` are checked against the
    scanned packs, and its Settings resolved, before the catalog is returned.
    A Setting resolves to its declared default, then the scene's override in
    its pack reference, then *setting_overrides*.

    *setting_overrides* mirrors ``scene.json`` per scene, keyed by pack name::

        {scene: {"settings": {name: value},
                 "rule_packs": {pack: {name: value}},
                 "effect_packs": {pack: {name: value}}}}

    Every key is optional. It is checked like the scene's own overrides; it is
    how the Simulated device and tests boot shortened scenes.

    Raises:
        PackScanError: the first problem found on disk or in
            *setting_overrides* (see its subclasses).
        ValueError: *setting_overrides* names a scene that was not scanned,
            or a scene's overrides are not shaped as above.
    """
    overrides = setting_overrides or {}
    effect_packs: list[_PackEntry] = []
    rule_packs: list[_PackEntry] = []
    scenes: dict[str, _SceneEntry] = {}
    root_paths: dict[str, str] = {}
    for given_root in roots:
        root = _path.normpath(given_root).rstrip("/")
        if not _path.isdir(root):
            raise MissingRootError(given_root)
        root_name = root.split("/")[-1]
        if root_name in root_paths:
            raise DuplicateNameError(root_name, root_paths[root_name], root)
        root_paths[root_name] = root
        _scan_packs(root, root_name, "effects", effect_packs)
        _scan_packs(root, root_name, "rules", rule_packs)
        _scan_scenes(root, root_name, scenes)
    _check_override_scenes(overrides, scenes)
    _check_declarations(scenes, effect_packs, rule_packs)
    _resolve_settings(scenes, effect_packs, rule_packs, overrides)
    for root_name, root in root_paths.items():
        _add_import_parent(root[: -len(root_name)])
    return PackCatalog(
        PackRegistry._from_packs(_EXPORT_ATTR["effects"], effect_packs),
        PackRegistry._from_packs(_EXPORT_ATTR["rules"], rule_packs),
        SceneRegistry._from_scenes(scenes),
        _pack_sounds(effect_packs),
    )


def _check_override_scenes(overrides: dict, scenes: dict[str, _SceneEntry]) -> None:
    for scene in overrides:
        if scene not in scenes:
            raise ValueError(
                f"setting override names unknown scene {scene!r}; "
                + f"known scenes: {', '.join(sorted(scenes))}"
            )


def _resolve_settings(
    scenes: dict[str, _SceneEntry],
    effect_packs: list[_PackEntry],
    rule_packs: list[_PackEntry],
    setting_overrides: dict[str, dict[str, dict]],
) -> None:
    effect_declarations = {entry.name: entry.declarations for entry in effect_packs}
    rule_declarations = {entry.name: entry.declarations for entry in rule_packs}
    for scene, entry in scenes.items():
        own, effects, rules = _read_setting_overrides(scene, setting_overrides.get(scene, {}))
        values = {
            _SCENE_NAMESPACE: _resolve_namespace(scene, _SCENE_NAMESPACE, entry.declarations, [own])
        }
        # Effect-pack Settings are checked, but effects do not receive them yet.
        _resolve_kind(scene, entry.effect_packs, effect_declarations, effects)
        values.update(_resolve_kind(scene, entry.rule_packs, rule_declarations, rules))
        entry.settings = Settings(values)


def _read_setting_overrides(
    scene: str, given: object
) -> tuple[dict[str, object], dict[str, dict], dict[str, dict]]:
    """Return *scene*'s ``settings``, ``effect_packs`` and ``rule_packs`` overrides."""
    if not isinstance(given, dict):
        raise ValueError(f"setting overrides for scene {scene!r} are not a dict")
    for key in given:
        if key not in _OVERRIDE_KEYS:
            raise ValueError(f"setting overrides for scene {scene!r} have unknown key {key!r}")
    parts = []
    for key in _OVERRIDE_KEYS:
        part = given.get(key, {})
        if not isinstance(part, dict):
            raise ValueError(f"setting overrides {key!r} for scene {scene!r} are not a dict")
        if key != "settings":
            for pack, values in part.items():
                if not isinstance(values, dict):
                    raise ValueError(
                        f"setting overrides for {key} {pack!r} of scene {scene!r} are not a dict"
                    )
        parts.append(part)
    return parts[0], parts[1], parts[2]


def _resolve_kind(
    scene: str,
    references: list[PackReference],
    declarations: dict[str, dict[str, SettingDeclaration]],
    given: dict[str, dict],
) -> dict[str, dict[str, object]]:
    declared = [reference.name for reference in references]
    for pack, values in given.items():
        if pack not in declared:
            for setting in values:
                raise SettingOverrideError(scene, pack, setting, "the scene does not declare it")
    return {
        reference.name: _resolve_namespace(
            scene,
            reference.name,
            declarations[reference.name],
            [reference.settings, given.get(reference.name, {})],
        )
        for reference in references
    }


def _resolve_namespace(
    scene: str,
    namespace: str,
    declarations: dict[str, SettingDeclaration],
    layers: list[dict[str, object]],
) -> dict[str, object]:
    try:
        return resolve_settings(declarations, layers)
    except SettingValueError as exc:
        raise SettingOverrideError(scene, namespace, exc.setting, exc.reason) from exc


def _check_declarations(
    scenes: dict[str, _SceneEntry],
    effect_packs: list[_PackEntry],
    rule_packs: list[_PackEntry],
) -> None:
    installed_effects = {entry.name: entry.version for entry in effect_packs}
    installed_rules = {entry.name: entry.version for entry in rule_packs}
    for scene, entry in scenes.items():
        _check_kind(scene, "effect", entry.effect_packs, installed_effects)
        _check_kind(scene, "rule", entry.rule_packs, installed_rules)


def _check_kind(
    scene: str,
    kind: str,
    references: list[PackReference],
    installed: dict[str, Version],
) -> None:
    for reference in references:
        pack = reference.name
        if pack not in installed:
            raise UnknownDeclaredPackError(scene, pack, kind)
        if not _is_compatible(installed[pack], reference.version):
            raise IncompatiblePackError(scene, pack, installed[pack], reference.version)


def _is_compatible(installed: Version, required: Version) -> bool:
    return installed.major == required.major and installed.minor >= required.minor


def _add_import_parent(parent: str) -> None:
    # A root's parent directory is what makes ``<root name>.<kind>...`` importable.
    # A bare relative root ("packs") has parent "", the current directory.
    if parent != "/":
        parent = parent.rstrip("/")
    if parent not in sys.path:
        sys.path.append(parent)


def _pack_sounds(effect_packs: list[_PackEntry]) -> dict[str, str]:
    sounds: dict[str, str] = {}
    for entry in effect_packs:
        for stem, path in _scan_sounds(_path.join(entry.source_path, "sounds")).items():
            sounds[entry.name + "." + stem] = path
    return sounds


def _scan_sounds(sound_dir: str) -> dict[str, str]:
    return _path.scan_stems(sound_dir, _SOUND_EXTENSIONS)


def _scan_packs(root: str, root_name: str, kind: str, packs: list[_PackEntry]) -> None:
    kind_dir = _path.join(root, kind)
    if not _path.isdir(kind_dir):
        return
    for name in os.listdir(kind_dir):
        pack_dir = _path.join(kind_dir, name)
        manifest_path = _path.join(pack_dir, _MANIFEST_NAME[kind])
        if not _path.isfile(manifest_path):
            continue
        if name == "scene":
            raise ReservedNameError(pack_dir)
        for entry in packs:
            if entry.name == name:
                raise DuplicateNameError(name, entry.source_path, pack_dir)
        manifest = _read_manifest(manifest_path)
        version = _parse_version(manifest.get("version"), manifest_path)
        packs.append(
            _PackEntry(
                name=name,
                version=version,
                module_prefix=root_name + "." + kind + "." + name,
                item_names=scan_item_names(pack_dir),
                source_path=pack_dir,
                declarations=read_manifest_declarations(manifest, manifest_path),
            )
        )


def _scan_scenes(
    root: str,
    root_name: str,
    scenes: dict[str, _SceneEntry],
) -> None:
    kind_dir = _path.join(root, "scenes")
    if not _path.isdir(kind_dir):
        return
    for name in os.listdir(kind_dir):
        scene_dir = _path.join(kind_dir, name)
        scene_json = _path.join(scene_dir, "scene.json")
        if not _path.isfile(scene_json):
            continue
        if name in scenes:
            raise DuplicateNameError(name, scenes[name].source_path, scene_dir)
        data = _read_scene_json(name, scene_json)
        scene_prefix = root_name + ".scenes." + name
        scenes[name] = _SceneEntry(
            version=_parse_version(data["version"], scene_json),
            effect_packs=_read_pack_references(name, scene_json, data, "effect_packs"),
            rule_packs=_read_pack_references(name, scene_json, data, "rule_packs"),
            source_path=scene_dir,
            ir_codec=_read_ir_codec(name, scene_json, data),
            local_rule_registry=_scan_local_items(scene_dir, scene_prefix, "rules"),
            local_effect_registry=_scan_local_items(scene_dir, scene_prefix, "effects"),
            local_sound_map=_scan_sounds(_path.join(scene_dir, "sounds")),
            declarations=_read_scene_declarations(name, scene_json, data),
        )


def _read_manifest(path: str) -> dict:
    with open(path) as fh:
        try:
            data = json.load(fh)
        except ValueError as exc:
            raise MalformedManifestError(path, f"invalid JSON ({exc})") from exc
    if not isinstance(data, dict):
        raise MalformedManifestError(path, "top level is not a JSON object")
    return data


def read_manifest_declarations(manifest: dict, path: str) -> dict[str, SettingDeclaration]:
    """Return the Setting declarations in the Pack *manifest* read from *path*.

    Raises:
        MalformedManifestError: its ``settings`` section is malformed.
    """
    try:
        return parse_declarations(manifest.get("settings", {}))
    except ValueError as exc:
        raise MalformedManifestError(path, str(exc)) from exc


def _read_scene_json(scene: str, path: str) -> dict:
    with open(path) as fh:
        try:
            data = json.load(fh)
        except ValueError as exc:
            raise MalformedSceneError(scene, path, f"invalid JSON ({exc})") from exc
    if not isinstance(data, dict):
        raise MalformedSceneError(scene, path, "top level is not a JSON object")
    for key in _REQUIRED_SCENE_KEYS:
        if key not in data:
            raise MalformedSceneError(scene, path, f"missing required key '{key}'")
    for key in data:
        if key not in _SCENE_KEYS:
            raise MalformedSceneError(scene, path, f"unknown key {key!r}")
    return data


def _read_scene_declarations(scene: str, path: str, data: dict) -> dict[str, SettingDeclaration]:
    try:
        return parse_declarations(data.get("settings", {}))
    except ValueError as exc:
        raise MalformedSceneError(scene, path, str(exc)) from exc


def _read_pack_references(scene: str, path: str, data: dict, key: str) -> list[PackReference]:
    entries = data[key]
    if not isinstance(entries, list):
        raise MalformedSceneError(scene, path, f"'{key}' is not a list")
    references: list[PackReference] = []
    for entry in entries:
        reference = _read_pack_reference(scene, path, key, entry)
        for earlier in references:
            if earlier.name == reference.name:
                raise MalformedSceneError(
                    scene, path, f"'{key}' declares pack '{reference.name}' twice"
                )
        references.append(reference)
    return references


def _read_pack_reference(scene: str, path: str, key: str, entry: object) -> PackReference:
    if not isinstance(entry, dict):
        raise MalformedSceneError(scene, path, f"'{key}' entry {entry!r} is not an object")
    for field in entry:
        if field not in _PACK_REFERENCE_KEYS:
            raise MalformedSceneError(scene, path, f"'{key}' entry has unknown key {field!r}")
    name = entry.get("name")
    if not isinstance(name, str):
        raise MalformedSceneError(scene, path, f"'{key}' entry {entry!r} has no string 'name'")
    if "version" not in entry:
        raise MalformedSceneError(scene, path, f"'{key}' entry for '{name}' has no 'version'")
    settings = entry.get("settings", {})
    if not isinstance(settings, dict):
        raise MalformedSceneError(
            scene, path, f"'{key}' entry for '{name}' has 'settings' that is not an object"
        )
    return PackReference(name, _parse_version(entry["version"], path), settings)


def _read_ir_codec(scene: str, path: str, data: dict) -> str:
    if "ir_codec" not in data:
        return "aura"
    ir_codec = data["ir_codec"]
    if not isinstance(ir_codec, str) or not ir_codec.strip():
        raise MalformedSceneError(scene, path, f"ir_codec {ir_codec!r} is not a non-empty string")
    return ir_codec


def _parse_version(value: object, path: str) -> Version:
    try:
        return Version.parse(value)
    except ValueError as exc:
        raise MalformedVersionError(path, value) from exc


def _scan_local_items(scene_dir: str, scene_prefix: str, kind: str) -> SceneLocalRegistry:
    item_dir = _path.join(scene_dir, kind)
    if not _path.isdir(item_dir):
        return SceneLocalRegistry()
    return SceneLocalRegistry._from_items(
        _EXPORT_ATTR[kind], scan_item_names(item_dir), scene_prefix + "." + kind
    )

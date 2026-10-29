"""Pack catalog — one scan of every pack root into the registries callers use."""

from __future__ import annotations

__all__ = [
    "DuplicateNameError",
    "MalformedSceneError",
    "MalformedVersionError",
    "MissingRootError",
    "PackCatalog",
    "PackScanError",
    "ReservedNameError",
    "scan_pack_roots",
]

import json
import os
import sys

import engine._path as _path
from engine.audio import scan_sound_dir
from engine.packs import PackRegistry, _PackEntry, scan_item_names
from engine.scene import SceneLocalRegistry, SceneRegistry, _SceneEntry
from engine.version import Version

_REQUIRED_SCENE_KEYS = ("version", "effect_packs", "rule_packs")


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
    """A version in *path* (``version.txt`` or ``scene.json``) is not ``'MAJOR.MINOR'``."""

    def __init__(self, path: str, value: object) -> None:
        self.path = path
        self.value = value
        super().__init__(f"Malformed version {value!r} in '{path}'; expected 'MAJOR.MINOR'")


class MalformedSceneError(PackScanError):
    """Scene *scene*'s ``scene.json`` at *path* cannot be used, for *reason*."""

    def __init__(self, scene: str, path: str, reason: str) -> None:
        self.scene = scene
        self.path = path
        self.reason = reason
        super().__init__(f"Scene '{scene}' has a malformed '{path}': {reason}")


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


def scan_pack_roots(roots: list[str]) -> PackCatalog:
    """Scan the pack *roots*, in order, into one ``PackCatalog``."""
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
    for root_name, root in root_paths.items():
        _add_import_parent(root[: -len(root_name)])
    return PackCatalog(
        PackRegistry._from_packs("BUILD", effect_packs),
        PackRegistry._from_packs("RULE", rule_packs),
        SceneRegistry._from_scenes(scenes),
        _pack_sounds(effect_packs),
    )


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
        for stem, path in scan_sound_dir(_path.join(entry.source_path, "sounds")).items():
            sounds[entry.name + "." + stem] = path
    return sounds


def _scan_packs(root: str, root_name: str, kind: str, packs: list[_PackEntry]) -> None:
    kind_dir = _path.join(root, kind)
    if not _path.isdir(kind_dir):
        return
    for name in os.listdir(kind_dir):
        pack_dir = _path.join(kind_dir, name)
        version_file = _path.join(pack_dir, "version.txt")
        if not _path.isfile(version_file):
            continue
        if name == "scene":
            raise ReservedNameError(pack_dir)
        for entry in packs:
            if entry.name == name:
                raise DuplicateNameError(name, entry.source_path, pack_dir)
        with open(version_file) as fh:
            version = _parse_version(fh.readline().strip(), version_file)
        packs.append(
            _PackEntry(
                name=name,
                version=version,
                module_prefix=root_name + "." + kind + "." + name,
                item_names=scan_item_names(pack_dir),
                source_path=pack_dir,
            )
        )


def _scan_scenes(root: str, root_name: str, scenes: dict[str, _SceneEntry]) -> None:
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
            effect_packs=data["effect_packs"],
            rule_packs=data["rule_packs"],
            initial_data=data.get("initial_data"),
            source_path=scene_dir,
            ir_codec=_read_ir_codec(name, scene_json, data),
            local_rule_registry=_scan_local_items(scene_dir, scene_prefix, "rules", "RULE"),
            local_effect_registry=_scan_local_items(scene_dir, scene_prefix, "effects", "BUILD"),
            local_sound_map=scan_sound_dir(_path.join(scene_dir, "sounds")),
        )


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
    return data


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


def _scan_local_items(
    scene_dir: str, scene_prefix: str, kind: str, item_attr: str
) -> SceneLocalRegistry:
    item_dir = _path.join(scene_dir, kind)
    if not _path.isdir(item_dir):
        return SceneLocalRegistry(item_attr)
    return SceneLocalRegistry._from_items(
        item_attr, scan_item_names(item_dir), scene_prefix + "." + kind
    )

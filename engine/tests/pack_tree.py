"""PackTree — lays out pack roots, packs and scenes on disk for catalog-backed tests.

The ``pack_tree`` fixture in the root ``conftest.py`` hands one out, rooted at
the test's ``tmp_path``, and undoes the import side effects of the scan.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from engine.pack_catalog import PackCatalog, scan_pack_roots


class PackTree:
    """Builds pack roots under *base*, each a real directory tree the catalog scans.

    Root names double as top-level import packages, so give each test root a
    name no real package uses (never ``packs``). Items are written as ``.py``
    files from the given source; sounds as placeholder ``.wav`` files.
    """

    def __init__(self, base: Path) -> None:
        self._base = base
        self.root_names: set[str] = set()

    def root(self, name: str, *, under: str = "roots") -> Path:
        """Create and return the pack root ``<base>/<under>/<name>``.

        Two roots with the same *name* need different *under* folders.
        """
        root = self._base / under / name
        root.mkdir(parents=True, exist_ok=True)
        self.root_names.add(name)
        return root

    def effect_pack(
        self,
        root: Path,
        name: str,
        *,
        version: str | None = "1.0",
        items: dict[str, str] | None = None,
        sounds: Iterable[str] = (),
    ) -> Path:
        """Create effect pack *name* under *root*; ``version=None`` omits ``version.txt``."""
        pack_dir = self._pack(root / "effects" / name, version, items)
        _write_sounds(pack_dir, sounds)
        return pack_dir

    def rule_pack(
        self,
        root: Path,
        name: str,
        *,
        version: str | None = "1.0",
        items: dict[str, str] | None = None,
    ) -> Path:
        """Create rule pack *name* under *root*; ``version=None`` omits ``version.txt``."""
        return self._pack(root / "rules" / name, version, items)

    def scene(
        self,
        root: Path,
        name: str,
        *,
        version: object = "1.0",
        effect_packs: list[list[str]] | None = None,
        rule_packs: list[list[str]] | None = None,
        effects: dict[str, str] | None = None,
        rules: dict[str, str] | None = None,
        sounds: Iterable[str] = (),
        scene_json: str | None = None,
        **fields: object,
    ) -> Path:
        """Create scene *name* under *root* and return its directory.

        ``scene.json`` is built from *version*, *effect_packs*, *rule_packs* and
        any extra *fields* (``ir_codec``, ``initial_data``), unless *scene_json*
        gives its raw text instead.
        """
        scene_dir = root / "scenes" / name
        scene_dir.mkdir(parents=True, exist_ok=True)
        if scene_json is None:
            data: dict[str, object] = {
                "version": version,
                "effect_packs": effect_packs or [],
                "rule_packs": rule_packs or [],
            }
            data.update(fields)
            scene_json = json.dumps(data)
        (scene_dir / "scene.json").write_text(scene_json)
        _write_items(scene_dir / "effects", effects)
        _write_items(scene_dir / "rules", rules)
        _write_sounds(scene_dir, sounds)
        return scene_dir

    def scan(
        self,
        *,
        effect_packs: dict[str, dict[str, str]] | None = None,
        rule_packs: dict[str, dict[str, str]] | None = None,
        scenes: dict[str, dict] | None = None,
    ) -> PackCatalog:
        """Lay out one root holding the given packs and scenes, and scan it.

        Packs map a pack name to its *items*; *scenes* map a scene name to its
        ``scene`` keyword arguments.
        """
        root = self.root("tp_tree")
        for name, items in (effect_packs or {}).items():
            self.effect_pack(root, name, items=items)
        for name, items in (rule_packs or {}).items():
            self.rule_pack(root, name, items=items)
        for name, fields in (scenes or {}).items():
            self.scene(root, name, **fields)
        return self.scan_roots(root)

    def scan_roots(self, *roots: Path) -> PackCatalog:
        """Scan *roots*, in order, into a ``PackCatalog``."""
        return scan_pack_roots([str(root) for root in roots])

    def _pack(self, pack_dir: Path, version: str | None, items: dict[str, str] | None) -> Path:
        pack_dir.mkdir(parents=True, exist_ok=True)
        if version is not None:
            (pack_dir / "version.txt").write_text(version + "\n")
        _write_items(pack_dir, items)
        return pack_dir


def _write_items(item_dir: Path, items: dict[str, str] | None) -> None:
    if not items:
        return
    item_dir.mkdir(parents=True, exist_ok=True)
    for item_name, source in items.items():
        (item_dir / (item_name + ".py")).write_text(source)


def _write_sounds(owner_dir: Path, stems: Iterable[str]) -> None:
    stems = list(stems)
    if not stems:
        return
    sounds_dir = owner_dir / "sounds"
    sounds_dir.mkdir(parents=True, exist_ok=True)
    for stem in stems:
        (sounds_dir / (stem + ".wav")).write_bytes(b"RIFF")

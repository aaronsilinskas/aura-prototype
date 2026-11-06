"""Resolve real Settings declarations plus test overrides, so tests never restate a default."""

from __future__ import annotations

import json
from pathlib import Path

from engine.pack_catalog import read_manifest_declarations, scan_pack_roots
from engine.settings import Settings, resolve_settings

_PACKS_ROOT = Path(__file__).resolve().parents[1]


def settings_for(
    scene: str | None = None,
    *,
    rule_packs: dict[str, dict[str, object]] | None = None,
    settings: dict[str, object] | None = None,
) -> Settings:
    """Return the Settings a rule reads, from the real declarations under ``packs/``.

    With *scene*, the whole ``packs`` root is scanned and that scene's Settings
    are returned, as the scene boots them, with *settings* (the scene's own, in
    the ``scene`` namespace) and *rule_packs* applied as the scan's
    ``setting_overrides``. Without *scene*, only the rule packs named in
    *rule_packs* resolve, each from its own manifest's defaults plus the
    overrides given for it (``{}`` for none).

    *rule_packs* is keyed by pack name, as in ``scene.json`` and
    ``setting_overrides``. An override is checked as at scan: a misspelled or
    mistyped one raises.

    Raises:
        SettingOverrideError: with *scene*, an override is bad.
        SettingValueError: without *scene*, an override is bad.
        ValueError: *settings* is given without *scene*.
    """
    rule_packs = rule_packs or {}
    if scene is not None:
        overrides = {scene: {"settings": settings or {}, "rule_packs": rule_packs}}
        catalog = scan_pack_roots([str(_PACKS_ROOT)], setting_overrides=overrides)
        return catalog.scene_registry.get(scene).settings
    if settings:
        raise ValueError("a scene's own settings need the scene named")
    values: dict[str, dict[str, object]] = {}
    for pack, overrides_for_pack in rule_packs.items():
        manifest_path = _PACKS_ROOT / "rules" / pack / "rules.json"
        manifest = json.loads(manifest_path.read_text())
        declarations = read_manifest_declarations(manifest, str(manifest_path))
        values[pack] = resolve_settings(declarations, [overrides_for_pack])
    return Settings(values)

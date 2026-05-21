"""Integration smoke tests: PackRegistry discovers the first-party packs under packs/."""

from __future__ import annotations

import os

from engine.packs import PackRegistry

_PACKS_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


def _packs_path(*parts: str) -> str:
    return os.path.join(_PACKS_ROOT, *parts)


def test_scan_effects_discovers_elements_pack() -> None:
    registry = PackRegistry(extractor=lambda module: module)
    registry.scan_dir(_packs_path("effects"), "packs.effects")
    # Verify the elements pack was discovered by attempting to access a known item
    module = registry.get("elements", "fire")
    assert hasattr(module, "build_fire_renderer")


def test_scan_rules_discovers_debug_pack() -> None:
    registry = PackRegistry(extractor=lambda module: module.rule)
    registry.scan_dir(_packs_path("rules"), "packs.rules")
    rule = registry.get("debug_pack", "button_events")
    from engine.engine import GameRule

    assert isinstance(rule, GameRule)


def test_scan_rules_debug_pack_event_logger_exports_rule() -> None:
    registry = PackRegistry(extractor=lambda module: module.rule)
    registry.scan_dir(_packs_path("rules"), "packs.rules")
    rule = registry.get("debug_pack", "event_logger")
    from engine.engine import GameRule

    assert isinstance(rule, GameRule)

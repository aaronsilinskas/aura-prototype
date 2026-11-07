"""The ``lobby`` pack's declared Settings, checked when the catalog is scanned."""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.pack_catalog import SettingOverrideError

_PACKS_ROOT = Path(__file__).resolve().parents[3]

SCOPES = ["personal"]
ENTRIES = [{"scene": "tag", "effect": "elements.fire"}]


def _scan_lobby_scene(pack_tree, settings: dict[str, object]) -> None:
    """Scan the real packs plus scene ``bare_lobby``, declaring ``lobby`` with *settings*."""
    root = pack_tree.root("ts_flash")
    reference = {"name": "lobby", "version": "1.0", "settings": settings}
    pack_tree.scene(root, "bare_lobby", rule_packs=[reference])
    pack_tree.scan_roots(_PACKS_ROOT, root)


@pytest.mark.parametrize(
    ("settings", "missing"),
    [({"entries": ENTRIES}, "scopes"), ({"scopes": SCOPES}, "entries")],
    ids=["no-scopes", "no-entries"],
)
def test_a_scene_declaring_lobby_without_scopes_or_entries_fails_the_scan(
    pack_tree, settings, missing
) -> None:
    with pytest.raises(SettingOverrideError) as excinfo:
        _scan_lobby_scene(pack_tree, settings)

    error = excinfo.value
    assert (error.scene, error.pack, error.setting) == ("bare_lobby", "lobby", missing)


@pytest.mark.parametrize("setting", ["scopes", "entries"])
def test_a_lobby_setting_that_is_not_a_list_fails_the_scan(pack_tree, setting) -> None:
    with pytest.raises(SettingOverrideError) as excinfo:
        _scan_lobby_scene(pack_tree, {"scopes": SCOPES, "entries": ENTRIES, setting: "personal"})

    assert excinfo.value.setting == setting

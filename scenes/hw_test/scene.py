from __future__ import annotations

from engine.scene import Scene
from engine.state import EffectControls, Scope
from packs.rules.hw_test.mode_rule import HwTestModeRule
from packs.rules.hw_test.motion_rule import HwTestMotionRule
from packs.rules.hw_test.network_rule import HwTestNetworkRule


def _on_unload(ec: EffectControls) -> None:
    ec.stop_effect(Scope.ALL)


def factory() -> Scene:
    """Create and return a fresh hw_test Scene instance."""
    return Scene(
        rules=[HwTestModeRule(), HwTestMotionRule(), HwTestNetworkRule()],
        effect_packs=[("elements", "1.0"), ("basic", "1.0")],
        rule_packs=[("debug", "1.0")],
        initial_data={"initial_mode": 0},
        on_unload=_on_unload,
    )

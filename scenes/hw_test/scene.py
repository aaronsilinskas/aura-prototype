from __future__ import annotations

from engine.scene import Scene
from engine.state import EffectControls, Scope


def _on_unload(ec: EffectControls) -> None:
    ec.stop_effect(Scope.ALL)


def factory() -> Scene:
    """Create and return a fresh hw_test Scene instance."""
    return Scene(
        effect_packs=[("elements", "1.0"), ("basic", "1.0")],
        rule_packs=[("hw_test", "1.0"), ("debug", "1.0")],
        initial_data={"initial_mode": 0},
        on_unload=_on_unload,
    )

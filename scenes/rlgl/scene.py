from __future__ import annotations

from engine.scene import Scene
from engine.state import EffectControls, Scope


def _on_unload(ec: EffectControls) -> None:
    ec.stop_effect(Scope.ALL)


def factory() -> Scene:
    return Scene(
        effect_packs=[("elements", "1.0"), ("basic", "1.1")],
        rule_packs=[("rlgl", "1.0")],
        on_unload=_on_unload,
    )

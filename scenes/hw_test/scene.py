from __future__ import annotations

from engine.scene import Scene


def factory() -> Scene:
    """Create and return a fresh hw_test Scene instance."""
    return Scene(
        effect_packs=[("elements", "1.0"), ("basic", "1.0"), ("hw_test", "1.0")],
        rule_packs=[("hw_test", "1.0"), ("debug", "1.0")],
        initial_data={"initial_mode": 0},
    )

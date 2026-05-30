from __future__ import annotations

from engine.packs import PackRegistry
from engine.scene import Scene
from engine.state import EffectControls, Scope


def _on_unload(ec: EffectControls) -> None:
    ec.stop_effect(Scope.ALL)


def factory() -> Scene:
    return Scene(
        effect_packs=[("elements", "1.0"), ("basic", "1.1"), ("rlgl", "1.0")],
        rule_packs=[("rlgl", "1.0")],
        on_unload=_on_unload,
    )


def create_audio_output(registry: PackRegistry):
    """Instantiate the AudioEffectOutput for the RLGL scene (hardware-only).

    Import is deferred so this module remains importable on CPython.
    """
    from hardware.circuitpython.audio_output import AudioEffectOutput

    return AudioEffectOutput(registry)

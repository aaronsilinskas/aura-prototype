"""Build card scenes and card packs on a Simulated device's card directory."""

from __future__ import annotations

import json
from pathlib import Path


def package(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "__init__.py").touch()
    return directory


def card_pack_dir(card: Path, kind: str, name: str) -> Path:
    """The package ``aura_packs/<kind>/<name>`` on *card*, made with every level above it."""
    return package(package(package(card / "aura_packs") / kind) / name)


def card_scene_dir(card: Path, scene: str, effect_pack: tuple[str, str] = ("basic", "1.1")) -> Path:
    """Card scene *scene*'s package, its ``scene.json`` naming *effect_pack* and no rule packs."""
    scene_dir = card_pack_dir(card, "scenes", scene)
    (scene_dir / "scene.json").write_text(
        json.dumps(
            {
                "version": "1.0",
                "effect_packs": [{"name": effect_pack[0], "version": effect_pack[1]}],
                "rule_packs": [],
            }
        )
    )
    return scene_dir


def audio_effect_source(clip: str, *, loop: bool) -> str:
    """Source of an effect module whose effect plays *clip* on start."""
    return f"""\
from effects.effect import AudioPlaybackConfig, Effect, EffectAudio, EffectConfig, EffectVerb
from engine.effects.builder import EffectBuilder

_AUDIO = EffectAudio(
    clips={{EffectVerb.START: AudioPlaybackConfig(name={clip!r}, loop={loop!r})}}
)


class _Builder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        return Effect(name=name, audio=_AUDIO)


BUILD = _Builder()
"""

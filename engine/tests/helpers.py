from __future__ import annotations

from typing import TYPE_CHECKING

from engine.audio import AudioOverlayAdmin
from engine.engine import GameEngine
from engine.pack_catalog import PackCatalog
from engine.scene import SceneManager
from engine.state import (
    EffectAdmin,
    EffectControls,
    EffectReceipt,
    NetworkControls,
    SceneReboot,
    ScopeValue,
)

if TYPE_CHECKING:
    pass

_STUB_RECEIPT_ID = 0


class SpyNetworkControls(NetworkControls):
    """Test spy that records send_ir and send_radio calls."""

    def __init__(self) -> None:
        self.send_ir_calls: list[tuple[bytes, str]] = []
        self.send_radio_calls: list[bytes] = []

    def send_ir(self, data: bytes, emitter: str) -> None:
        self.send_ir_calls.append((data, emitter))

    def send_radio(self, data: bytes) -> None:
        self.send_radio_calls.append(data)


class SpyEffectControls(EffectControls):
    """Test spy that records set_effect, stop_effect, and add_effect calls.

    ``add_effect`` stubs with a dummy ``EffectReceipt``. ``set_merge_strategy``
    is a defensive no-op: this spy is for rule unit tests, which may call it,
    but has no merge-strategy state of its own to record it against.
    """

    def __init__(self) -> None:
        self.set_effect_calls: list[tuple[ScopeValue, str, dict]] = []
        self.stop_effect_calls: list[ScopeValue] = []
        self.add_effect_calls: list[tuple[ScopeValue, str, dict]] = []

    def set_effect(self, scope: ScopeValue, name: str, options: dict[str, object]) -> EffectReceipt:
        self.set_effect_calls.append((scope, name, options))
        return EffectReceipt(_STUB_RECEIPT_ID)

    def add_effect(self, scope: ScopeValue, name: str, options: dict[str, object]) -> EffectReceipt:
        self.add_effect_calls.append((scope, name, options))
        return EffectReceipt(_STUB_RECEIPT_ID)

    def stop_effect(self, scope: ScopeValue) -> None:
        self.stop_effect_calls.append(scope)

    def set_merge_strategy(self, scope: ScopeValue, strategy: object) -> None:
        pass  # no-op: SpyEffectControls has no merge-strategy state to record


class SpyEffectAdmin(EffectAdmin):
    """Test recorder for the scene-transition ``EffectAdmin`` face.

    Records every ``set_local_effects``/``set_allowed_packs`` push and
    merge-strategy lifecycle call so ``SceneManager`` transition tests can
    assert on them without wiring a real ``EffectManager``.
    ``capture_merge_strategies`` returns a fresh empty dict each call (a
    harmless placeholder snapshot) since this spy carries no live
    merge-strategy state of its own.
    """

    def __init__(self) -> None:
        self.local_effects_history: list[object] = []
        self.allowed_packs_history: list[frozenset[str] | None] = []
        self.reset_merge_strategies_calls: int = 0
        self.capture_merge_strategies_calls: int = 0
        self.applied_snapshots: list[dict] = []

    def set_local_effects(self, local_registry: object) -> None:
        self.local_effects_history.append(local_registry)

    def set_allowed_packs(self, names: frozenset[str] | None) -> None:
        self.allowed_packs_history.append(names)

    def reset_merge_strategies(self) -> None:
        self.reset_merge_strategies_calls += 1

    def capture_merge_strategies(self) -> dict:
        self.capture_merge_strategies_calls += 1
        return {}

    def apply_merge_strategies(self, snapshot: dict) -> None:
        self.applied_snapshots.append(snapshot)


class SpyAudioOverlayAdmin(AudioOverlayAdmin):
    """Test recorder for the scene-transition ``AudioOverlayAdmin`` face.

    Records every ``set_scene_sounds``/``set_allowed_packs`` push so
    ``SceneManager`` transition tests can assert on them without wiring a
    real ``AudioRegistry``.
    """

    def __init__(self) -> None:
        self.scene_sounds_history: list[dict[str, str] | None] = []
        self.allowed_packs_history: list[frozenset[str] | None] = []

    def set_scene_sounds(self, sounds: dict[str, str] | None) -> None:
        self.scene_sounds_history.append(sounds)

    def set_allowed_packs(self, names: frozenset[str] | None) -> None:
        self.allowed_packs_history.append(names)


class RecordingSceneReboot(SceneReboot):
    """Test recorder for the board-free ``SceneReboot`` port.

    Records every ``reboot_into``/``reboot_to_previous`` call instead of
    touching storage or resetting anything, so ``SceneManager``'s
    validate-then-delegate behaviour is testable without a live
    ``DeviceSceneReboot``.
    """

    def __init__(self) -> None:
        self.reboot_into_calls: list[str] = []
        self.reboot_to_previous_calls: int = 0

    def reboot_into(self, target: str) -> None:
        self.reboot_into_calls.append(target)

    def reboot_to_previous(self) -> None:
        self.reboot_to_previous_calls += 1


def rule_source(class_name: str = "ARule") -> str:
    """Return the source of a rule item whose ``RULE`` is an instance of a fresh *class_name*."""
    return (
        "from engine.engine import GameRule\n"
        "class " + class_name + "(GameRule): pass\n"
        "RULE = " + class_name + "()\n"
    )


def make_scene_manager(
    catalog: PackCatalog,
    *,
    engine: GameEngine | None = None,
    effect_admin: SpyEffectAdmin | None = None,
    audio_overlay_admin: SpyAudioOverlayAdmin | None = None,
) -> SceneManager:
    """Construct a ``SceneManager`` over *catalog*'s registries, with spies for every port."""
    return SceneManager(
        engine or GameEngine(effect_controls=SpyEffectControls()),
        catalog.effect_registry,
        catalog.rule_registry,
        catalog.scene_registry,
        effect_admin or SpyEffectAdmin(),
        audio_overlay_admin or SpyAudioOverlayAdmin(),
        RecordingSceneReboot(),
    )

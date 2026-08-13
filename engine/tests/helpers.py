from __future__ import annotations

from engine.audio import AudioOverlayAdmin
from engine.state import EffectAdmin, EffectControls, EffectReceipt, NetworkControls, ScopeValue

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

    Records every ``set_local_effects`` push and merge-strategy lifecycle call
    so ``SceneManager`` transition tests can assert on them without wiring a
    real ``EffectManager``. ``capture_merge_strategies`` returns a fresh empty
    dict each call (a harmless placeholder snapshot) since this spy carries no
    live merge-strategy state of its own.
    """

    def __init__(self) -> None:
        self.local_effects_history: list[object] = []
        self.reset_merge_strategies_calls: int = 0
        self.capture_merge_strategies_calls: int = 0
        self.applied_snapshots: list[dict] = []

    def set_local_effects(self, local_registry: object) -> None:
        self.local_effects_history.append(local_registry)

    def reset_merge_strategies(self) -> None:
        self.reset_merge_strategies_calls += 1

    def capture_merge_strategies(self) -> dict:
        self.capture_merge_strategies_calls += 1
        return {}

    def apply_merge_strategies(self, snapshot: dict) -> None:
        self.applied_snapshots.append(snapshot)


class SpyAudioOverlayAdmin(AudioOverlayAdmin):
    """Test recorder for the scene-transition ``AudioOverlayAdmin`` face.

    Records every ``set_scene_sounds`` push so ``SceneManager`` transition
    tests can assert on it without wiring a real ``AudioRegistry``.
    """

    def __init__(self) -> None:
        self.scene_sounds_history: list[dict[str, str] | None] = []

    def set_scene_sounds(self, sounds: dict[str, str] | None) -> None:
        self.scene_sounds_history.append(sounds)

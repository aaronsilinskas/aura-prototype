from __future__ import annotations

from engine.state import EffectControls, EffectReceipt, NetworkControls, ScopeValue

_STUB_RECEIPT_ID = 0


class SpyNetworkControls(NetworkControls):
    """Test spy that records send_ir and send_radio calls."""

    def __init__(self) -> None:
        self.send_ir_calls: list[tuple[bytes, str]] = []
        self.send_radio_calls: list[bytes] = []

    def send_ir(self, data: bytes, emitter: str) -> bool:
        self.send_ir_calls.append((data, emitter))
        return True  # always "sends" synchronously from the test's perspective

    def send_radio(self, data: bytes) -> None:
        self.send_radio_calls.append(data)


class SpyEffectControls(EffectControls):
    """Test spy that records set_effect, stop_effect, and add_effect calls.

    ``add_effect`` stubs with a dummy ``EffectReceipt``.
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

    def set_local_effects(self, local_registry: object) -> None:
        pass  # no-op: SpyEffectControls is for rule unit tests, not SceneManager

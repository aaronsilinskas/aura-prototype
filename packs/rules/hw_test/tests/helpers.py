from __future__ import annotations

from engine.state import EffectControls, EffectReceipt, ScopeValue

_STUB_RECEIPT_ID = 0


class SpyEffectControls(EffectControls):
    """Test spy that records set_effect, stop_effect, and stop_effect_by_receipt calls.

    ``add_effect`` stubs with a dummy ``EffectReceipt``.
    """

    def __init__(self) -> None:
        self.set_effect_calls: list[tuple[ScopeValue, str, int, dict]] = []
        self.stop_effect_calls: list[ScopeValue] = []
        self.stop_effect_by_receipt_calls: list[EffectReceipt] = []
        self.add_effect_calls: list[tuple[ScopeValue, str, int, dict]] = []

    def set_effect(
        self, scope: ScopeValue, name: str, level: int, options: dict[str, object]
    ) -> EffectReceipt:
        self.set_effect_calls.append((scope, name, level, options))
        return EffectReceipt(_STUB_RECEIPT_ID)

    def add_effect(
        self, scope: ScopeValue, name: str, level: int, options: dict[str, object]
    ) -> EffectReceipt:
        self.add_effect_calls.append((scope, name, level, options))
        return EffectReceipt(_STUB_RECEIPT_ID)

    def stop_effect(self, scope: ScopeValue) -> None:
        self.stop_effect_calls.append(scope)

    def stop_effect_by_receipt(self, receipt: EffectReceipt) -> None:
        self.stop_effect_by_receipt_calls.append(receipt)

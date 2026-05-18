"""Scope routing constants for ``EffectManager``.

Pass a ``ScopeValue`` from ``Scope`` to ``EffectManager.set_effect`` or
``add_effect`` to control which outputs (visual, audio, haptic) receive an effect.
Composite scopes (e.g. ``Scope.ALL``) expand to the union of their members,
so a single call can target multiple areas at once.
"""

try:
    from typing import Final
except ImportError:
    pass  # Not available on CircuitPython


class ScopeValue:
    """A routing token that identifies one or more outputs.

    Routing model:
      - ``keys`` is the flat tuple of routing strings ``EffectManager`` iterates
        to dispatch to outputs.  Leaf scopes have one key; composite scopes
        expand to the union of their members' keys.
      - ``members`` holds the constituent ``ScopeValue`` instances.  For leaf
        scopes ``members == [self]``.
    Construction:
      - Use the constants on ``Scope`` rather than constructing directly.
    """

    __slots__ = ("_value", "keys", "members")

    def __init__(self, value: str, members: "list[ScopeValue] | None" = None) -> None:
        self._value: str = value
        if members is None:
            self.members: list[ScopeValue] = [self]
            self.keys: tuple[str, ...] = (value,)
        else:
            self.members = members
            self.keys = tuple(k for m in self.members for k in m.keys)

    def __repr__(self) -> str:
        return self._value


class Scope:
    """Namespace of ``ScopeValue`` constants for routing effects to outputs.

    Usage:
      - ``PERSONAL`` — local player's device only.
      - ``DIRECTIONAL`` — the direction indicator the player is pointing.
      - ``Global.*`` — shared outputs targeting all players.
      - ``ALL`` — every output; use when the scope should be universal
        (e.g. clearing all active effects).
    """

    class Global:
        """Shared outputs that target all players.

        Use ``MAIN``, ``BUFF``, or ``DEBUFF`` to target a specific zone.
        Use ``ALL`` to address every global zone without differentiation.
        """

        MAIN: "Final" = ScopeValue("global.main")  # primary effect area (e.g. active spell)
        BUFF: "Final" = ScopeValue("global.buff")  # positive status effects
        DEBUFF: "Final" = ScopeValue("global.debuff")  # negative status effects
        ALL: "Final" = ScopeValue(
            "global.all", [MAIN, BUFF, DEBUFF]
        )  # entire global area, no differentiation

    PERSONAL: "Final" = ScopeValue("personal")  # only the local player's device
    DIRECTIONAL: "Final" = ScopeValue("directional")  # the direction the player is pointing
    ALL: "Final" = ScopeValue(
        "all", [PERSONAL, DIRECTIONAL, Global.ALL]
    )  # every scope, including all global zones

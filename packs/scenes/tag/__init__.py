"""Tag scene package: effect-scope usage map.

The Tag scene drives several ``Scope`` channels for felt and visual feedback
across the four-phase machine documented in
:mod:`packs.scenes.tag.rules.helpers.phases`. This list is the authoritative,
discoverable map of which scope carries which effect(s), which rule owns each
one, and how long the effect lives — so a developer does not have to piece it
together by reading every rule.

- ``PERSONAL`` — ``basic.progress`` (hitpoints). Set up and torn down by
  ``TagPlayingRule``; re-issued by ``TagHitRule`` on each hit. Lives for the
  Playing phase, updated transiently on each hit.
- ``DIRECTIONAL`` — ``scene.fire_shot``. Owned by ``TagShootingRule``.
  Transient, per shot fired.
- ``Global.MAIN`` — ``scene.hit``. Owned by ``TagHitRule``. Transient, per
  hit received.
- ``Global.BUFF`` — a single mutually-exclusive "what's currently shown for
  ammo" slot: ``basic.progress`` (amber ammo bar), ``scene.ammo_empty`` (red
  pulse), ``scene.reload``, and ``scene.reload_complete`` all swap each other
  out via ``set_effect``. Set up by ``TagPlayingRule`` on Playing entry;
  ``TagShootingRule`` updates it on fire and drives
  ``scene.reload``/``scene.reload_complete`` while reloading. Torn down as a
  whole by ``TagPlayingRule`` via ``stop_effect(Scope.Global.BUFF)`` on exit —
  no receipt is stored, since any of the above effects (or none) may occupy
  the slot at the time.
- ``ALL`` — ``scene.ready``, owned by ``TagReadyRule``. Lives for the Ready
  phase.
- ``ALL`` — ``scene.warning_pulse``, owned by ``TagStartingRule``. Lives for
  the Starting phase.
- ``ALL`` — ``elements.fire`` then ``scene.game_over_sting``, both owned by
  ``TagGameOverRule``. Live for the Game Over phase.

Notes:

- ``Global.BUFF``'s ammo bar reads amber (``basic.progress``, ``0xFFBF00``)
  whenever it shows a non-empty value: full on Playing entry, updated after
  each shot that leaves ammo > 0, and full again on reload completion. The
  moment ammo reaches zero — the last shot or a cancelled reload — it switches
  to the self-looping ``scene.ammo_empty`` red pulse instead of a static empty
  ``basic.progress`` bar. Starting a reload replaces the pulse with
  ``scene.reload``, which takes the scope.
- ``Global.MAIN``'s ``scene.hit`` and ``DIRECTIONAL``'s ``scene.fire_shot``
  are one-shot felt-feedback effects, not bound to a phase's lifecycle.

See also:

- :class:`~packs.scenes.tag.rules.playing_rule.TagPlayingRule`
- :class:`~packs.scenes.tag.rules.shooting_rule.TagShootingRule`
- :class:`~packs.scenes.tag.rules.hit_rule.TagHitRule`
- :class:`~packs.scenes.tag.rules.ready_rule.TagReadyRule`
- :class:`~packs.scenes.tag.rules.starting_rule.TagStartingRule`
- :class:`~packs.scenes.tag.rules.game_over_rule.TagGameOverRule`
"""

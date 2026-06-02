"""RLGL ready effect.

Reuses :mod:`packs.effects.elements.water` directly.  The sound file
``water_peak.wav`` is resolved from the effect's *name* by
:class:`~engine.packs.PackRegistry`, not from the Python class name, so no
distinct effect class is required.
"""

from packs.effects.elements.water import BUILD  # noqa: F401

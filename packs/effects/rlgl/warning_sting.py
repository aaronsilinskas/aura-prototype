"""RLGL warning sting effect.

Reuses :mod:`packs.effects.basic.pulse` directly.  The sound file
``warning_sting_peak.wav`` is resolved from the effect's *name* by
:class:`~engine.packs.PackRegistry`, not from the Python class name, so no
distinct effect class is required.
"""

from packs.effects.basic.pulse import BUILD  # noqa: F401

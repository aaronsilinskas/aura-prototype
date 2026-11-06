try:
    from typing import Final
except ImportError:
    pass  # Not available on CircuitPython/MicroPython

NAMESPACE: Final = "debug"
"""The ``debug`` pack's Settings namespace, shared by its rules."""

"""Host-only stand-in for the device's built-in ``micropython`` module.

Lets CPython (the tests, the Simulated device) and mypy import code that uses
``@micropython.native``. On the device, ``mpy-cross`` consumes that decorator at
compile time and the firmware's built-in module takes over, so this file is
never deployed or compiled for the device and may use syntax the device can't.

mypy resolves ``micropython`` to this module rather than the
``circuitpython-stubs`` stub, which declares only ``const``. That stub is right
for the device, where ``native`` doesn't exist at runtime, so this is a
deliberate exception to the rule against local copies of real stubs (see
``typings/README.md``). It must stay a top-level module named ``micropython``:
``mpy-cross`` recognizes the decorator only when spelled ``@micropython.native``.
"""

from collections.abc import Callable
from typing import Any, TypeVar

_Function = TypeVar("_Function", bound=Callable[..., Any])
_Value = TypeVar("_Value")


def native(function: _Function) -> _Function:
    """Return *function* unchanged; only ``mpy-cross`` gives the decorator meaning."""
    return function


def const(value: _Value) -> _Value:
    """Return *value* unchanged, as the device's ``const`` does at runtime."""
    return value

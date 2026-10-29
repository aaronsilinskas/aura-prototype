"""Fixtures shared by every test tree: the harness's own tests and every pack's."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from app.simulation import Simulation


@pytest.fixture()
def simulation() -> Iterator[Simulation]:
    """A ``Simulation``, closed after the test so it leaves nothing behind."""
    # Imported here, not at module level, so test trees that never simulate
    # don't load the scene composition layer.
    from app.simulation import Simulation

    with Simulation() as simulation:
        yield simulation

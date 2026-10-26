from __future__ import annotations

import pytest

from app.simulation import Simulation


@pytest.fixture()
def sim() -> Simulation:
    return Simulation()

"""Test-only Simulation test harness: boots real scenes on simulated devices.
Never deployed; no shipped package may import it."""

from app.simulation.harness import TICK, SimulatedDevice, Simulation

__all__ = ["TICK", "SimulatedDevice", "Simulation"]

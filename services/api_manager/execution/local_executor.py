"""Compatibility shim for local execution.

The canonical implementation now belongs to simulation_worker.
"""

from services.simulation_worker.executor import (
    LocalSimulationExecutor,
)

__all__ = ["LocalSimulationExecutor"]